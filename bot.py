import os
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import requests
from aiohttp import web

# Load env
load_dotenv()

# ---- FIXED: AD_URL MUST EXIST ----
AD_URL = os.getenv("AD_URL", "https://adrinolinks.in")  # fallback URL

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bot")

# Config
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
TOKEN_VALIDITY_HOURS = int(os.getenv("TOKEN_VALIDITY_HOURS", 12))
ADRINOLINKS_API_KEY = os.getenv("ADRINOLINKS_API_KEY")
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", 0))
PORT = int(os.getenv("PORT", 8000))

# Bot Init
app = Client("token_ad_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Mongo
mongo = MongoClient(MONGODB_URI)
db = mongo["telegram_bot"]
users = db["users"]
videos = db["videos"]

users.create_index("user_id", unique=True)
videos.create_index("file_id", unique=True)

# =========================
# Helper functions
# =========================

async def get_user(uid):
    return users.find_one({"user_id": uid})

async def create_user(uid, username=None):
    data = {
        "user_id": uid,
        "username": username,
        "has_token": False,
        "token_expires_at": None,
        "videos_uploaded": 0,
        "joined_at": datetime.utcnow()
    }
    users.insert_one(data)
    return data

async def is_token_valid(uid):
    u = await get_user(uid)
    if not u or not u.get("has_token"):
        return False
    if not u.get("token_expires_at"):
        return False
    return datetime.utcnow() < u["token_expires_at"]

async def activate_token(uid):
    exp = datetime.utcnow() + timedelta(hours=TOKEN_VALIDITY_HOURS)
    users.update_one({"user_id": uid}, {"$set": {
        "has_token": True,
        "token_expires_at": exp
    }})
    return exp

async def save_video(fid, uid, fname):
    if videos.find_one({"file_id": fid}):
        return
    videos.insert_one({
        "file_id": fid,
        "user_id": uid,
        "file_name": fname,
        "uploaded_at": datetime.utcnow()
    })

async def shorten_url(long_url):
    try:
        import urllib.parse
        encoded = urllib.parse.quote(long_url, safe='')
        api = f"https://adrinolinks.in/api?api={ADRINOLINKS_API_KEY}&url={encoded}&format=text"
        r = requests.get(api, timeout=10)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
        return long_url
    except:
        return long_url


# =========================
# START COMMAND
# =========================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    uid = message.from_user.id
    uname = message.from_user.username

    # Deep-link handler
    if len(message.command) > 1:
        raw = message.command[1]

        # ---- Token Verification ----
        if raw.startswith("verify_"):
            await activate_token(uid)
            await message.reply_text("✅ Token activated! Use /upload now.")
            return

        # ---- Video Access ----
        try:
            import base64
            missing = len(raw) % 4
            if missing:
                raw += "=" * (4 - missing)

            decoded = base64.b64decode(raw).decode()
            if decoded.startswith("get-"):
                file_id = decoded.replace("get-", "")

                # Check token
                if not await is_token_valid(uid):
                    bot_username = (await client.get_me()).username
                    verify_link = f"https://t.me/{bot_username}?start=verify_{uid}"
                    ad = await shorten_url(verify_link)

                    return await message.reply(
                        "🎟 Token required! Watch ad to continue.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📺 Watch Ad", url=ad)]
                        ])
                    )

                video = videos.find_one({"file_id": file_id})
                if not video:
                    return await message.reply("❌ Video not found.")

                await message.reply("📥 Sending your file...")
                await client.send_video(uid, file_id, caption="🎬 Here is your video")
                return

        except Exception as e:
            return await message.reply(f"❌ Link decode failed: {e}")

    # Create user if new
    user = await get_user(uid)
    if not user:
        user = await create_user(uid, uname)

    # Normal start message
    if await is_token_valid(uid):
        exp = user["token_expires_at"]
        hrs = int((exp - datetime.utcnow()).total_seconds() / 3600)

        return await message.reply(
            f"✅ Welcome!\nToken Active ({hrs}h left)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Upload", callback_data="upload")],
                [InlineKeyboardButton("📊 Stats", callback_data="stats")]
            ])
        )
    else:
        bot_username = (await client.get_me()).username
        verify_link = f"https://t.me/{bot_username}?start=verify_{uid}"
        ad = await shorten_url(verify_link)

        return await message.reply(
            "👋 Welcome!\nToken inactive — watch ad to activate.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 Activate Token", url=ad)]
            ])
        )
        # =========================
# Part 2: Upload, handlers, callbacks, cleanup, server, main
# =========================

@app.on_message(filters.command("upload") & filters.private)
async def upload_command(client, message: Message):
    uid = message.from_user.id

    # Admin only (as per your previous logic)
    if uid != ADMIN_ID:
        return await message.reply_text("❌ Sirf admin video upload kar sakta hai.")

    # Ask admin to send video (just a prompt)
    await message.reply_text(
        "📤 Video bhejo (MP4/MKV). Bot upload karke link dega."
    )


@app.on_message(filters.video & filters.private)
async def handle_video(client, message: Message):
    uid = message.from_user.id

    # Admin-only
    if uid != ADMIN_ID:
        return await message.reply_text("❌ Sirf admin video upload kar sakta hai.")

    processing = await message.reply_text("⏳ Processing...")
    try:
        # Forward to storage channel if configured
        if STORAGE_CHANNEL_ID and STORAGE_CHANNEL_ID != 0:
            try:
                forwarded = await message.forward(STORAGE_CHANNEL_ID)
                file_id = forwarded.video.file_id
                logger.info(f"Forwarded to storage channel, file_id={file_id}")
            except Exception as e:
                logger.warning(f"Forward failed: {e} — using direct file_id")
                file_id = message.video.file_id
        else:
            file_id = message.video.file_id

        # Save to DB (skip duplicates)
        await save_video(file_id, uid, message.video.file_name or "video.mp4")

        # Update uploader stats (ensure user record exists)
        if not await get_user(uid):
            await create_user(uid, message.from_user.username)
        users.update_one({"user_id": uid}, {"$inc": {"videos_uploaded": 1}})

        # Make shareable base64 link
        import base64
        raw = f"get-{file_id}".encode()
        encoded = base64.b64encode(raw).decode()

        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded}"

        await processing.edit_text(
            f"✅ Video uploaded!\n\nShareable link:\n`{share_link}`\n\n"
            "Jab user link click karega to bot check karega token aur agar valid hoga to video bhej dega."
        )

    except Exception as exc:
        logger.error(f"Error in handle_video: {exc}", exc_info=True)
        try:
            await processing.edit_text("❌ Error uploading video. Check logs.")
        except:
            pass


@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message: Message):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user:
        return await message.reply_text("❌ User record nahi mila. /start karo pehle.")

    has_token = await is_token_valid(uid)
    token_text = "✅ Active" if has_token else "❌ Inactive"
    videos_count = user.get("videos_uploaded", 0)

    await message.reply_text(
        f"📊 Your Stats\n\n"
        f"👤 User ID: `{uid}`\n"
        f"🎟 Token: {token_text}\n"
        f"🎬 Videos uploaded: `{videos_count}`\n"
        f"📅 Joined: {user['joined_at'].strftime('%d %b %Y')}"
    )


@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    help_text = (
        "❓ Help\n\n"
        "/start - Start bot\n"
        "/upload - Admin only: upload video\n"
        "/stats - Your stats\n"
        "/help - This message\n\n"
        "Token system: Token 12 hours valid rehta hai. Token activate karne ke liye ad dekho."
    )
    await message.reply_text(help_text)


# Callback handlers (for inline buttons)
@app.on_callback_query(filters.regex("^verify_token$"))
async def cb_verify_token(client, cq: CallbackQuery):
    # We show an alert telling user to click the ad button, because activation must be via deep-link
    await cq.answer(
        "Ad pe click karke token activate karo (Open Ad, phir Verify button).",
        show_alert=True
    )


@app.on_callback_query(filters.regex("^upload$"))
async def cb_upload(client, cq: CallbackQuery):
    if cq.from_user.id != ADMIN_ID:
        await cq.answer("❌ Sirf admin use kar sakta hai.", show_alert=True)
        return
    await cq.message.reply_text("📤 Admin: Video bhejo (reply to this message with video).")
    await cq.answer()


@app.on_callback_query(filters.regex("^stats$"))
async def cb_stats(client, cq: CallbackQuery):
    uid = cq.from_user.id
    user = await get_user(uid)
    if not user:
        return await cq.answer("User not found. Use /start.", show_alert=True)
    has_token = await is_token_valid(uid)
    token_text = "✅ Active" if has_token else "❌ Inactive"
    await cq.answer(f"Token: {token_text}\nVideos: {user.get('videos_uploaded',0)}", show_alert=True)


# Cleanup task: expire tokens
async def cleanup_task():
    while True:
        try:
            res = users.update_many(
                {"token_expires_at": {"$lt": datetime.utcnow()}},
                {"$set": {"has_token": False, "token_expires_at": None}}
            )
            if getattr(res, "modified_count", 0):
                logger.info(f"Cleanup: expired {res.modified_count} tokens")
        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)
        await asyncio.sleep(3600)  # every hour


# Admin broadcast (example)
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_command(client, message: Message):
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply_text("Usage: /broadcast <text> or reply to a message to broadcast.")

    if message.reply_to_message:
        to_send = message.reply_to_message
    else:
        to_send_text = message.text.split(None, 1)[1]
        to_send = to_send_text

    total = 0
    succ = 0
    fail = 0
    cursor = users.find({}, {"user_id": 1})
    for u in cursor:
        total += 1
        try:
            if isinstance(to_send, str):
                await client.send_message(u["user_id"], to_send)
            else:
                await to_send.copy(chat_id=u["user_id"])
            succ += 1
        except Exception:
            fail += 1
    await message.reply_text(f"Broadcast done — total:{total} success:{succ} failed:{fail}")


# Bot stats (admin)
@app.on_message(filters.command("botstats") & filters.user(ADMIN_ID))
async def bot_stats_command(client, message: Message):
    total_users = users.count_documents({})
    active_tokens = users.count_documents({"token_expires_at": {"$gt": datetime.utcnow()}})
    total_videos = videos.count_documents({})
    await message.reply_text(
        f"🤖 Bot Stats\n\nUsers: {total_users}\nActive tokens: {active_tokens}\nTotal videos: {total_videos}"
    )


# Health HTTP server for Render / other hosts
async def health(request):
    return web.Response(text="OK")

async def start_http_server():
    app_web = web.Application()
    app_web.router.add_get("/", health)
    app_web.router.add_get("/health", health)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"HTTP server running on port {PORT}")


# Main: start bot + background tasks
async def main():
    await app.start()
    logger.info("Bot started.")
    # Start HTTP server
    asyncio.create_task(start_http_server())
    # Start cleanup task
    asyncio.create_task(cleanup_task())
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Run the main coroutine with pyrogram's run helper
    app.run(main())
