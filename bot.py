# bot.py (fixed, copy-paste ready)
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
import base64
import urllib.parse

# Load env
load_dotenv()

# ---- CONFIG / FALLBACKS ----
AD_URL = os.getenv("AD_URL", "https://adrinolinks.in")  # fallback URL
ADRINOLINKS_API_KEY = os.getenv("ADRINOLINKS_API_KEY")  # optional

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bot")

# Required config (ensure env has these)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TOKEN_VALIDITY_HOURS = int(os.getenv("TOKEN_VALIDITY_HOURS", "12"))
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))
PORT = int(os.getenv("PORT", "8000"))

# -------------------------
# Pyrogram client
# -------------------------
app = Client("token_ad_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------
# MongoDB (pymongo)
# -------------------------
mongo = MongoClient(MONGODB_URI)
db = mongo["telegram_bot"]
users = db["users"]
videos = db["videos"]

# Ensure indexes (idempotent)
try:
    users.create_index("user_id", unique=True)
    videos.create_index("file_id", unique=True)
except Exception as e:
    logger.warning(f"Index creation warning: {e}")

# -------------------------
# Helpers
# -------------------------
def _ensure_base64_padding(s: str) -> str:
    """Add '=' padding for base64 if needed"""
    return s + '=' * ((4 - len(s) % 4) % 4)

async def get_user(uid: int):
    """Return user document (or None). Note: pymongo is sync."""
    return users.find_one({"user_id": uid})

async def create_user(uid: int, username: str = None):
    """Insert a new user if not exists."""
    doc = {
        "user_id": uid,
        "username": username,
        "has_token": False,
        "token_expires_at": None,
        "last_ad_view": None,
        "videos_uploaded": 0,
        "joined_at": datetime.utcnow()
    }
    try:
        users.insert_one(doc)
    except Exception:
        # ignore duplicate insertion race
        pass
    return users.find_one({"user_id": uid})

async def is_token_valid(uid: int) -> bool:
    u = await get_user(uid)
    if not u or not u.get("has_token"):
        return False
    expires_at = u.get("token_expires_at")
    if not expires_at:
        return False
    # expires_at is a datetime stored in Mongo
    return datetime.utcnow() < expires_at

async def activate_token(uid: int):
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_VALIDITY_HOURS)
    users.update_one({"user_id": uid}, {"$set": {
        "has_token": True,
        "token_expires_at": expires_at,
        "last_ad_view": datetime.utcnow()
    }}, upsert=True)
    return expires_at

async def needs_ad_view(uid: int) -> bool:
    u = await get_user(uid)
    if not u:
        return True
    last = u.get("last_ad_view")
    if not last:
        return True
    return datetime.utcnow() - last > timedelta(hours=TOKEN_VALIDITY_HOURS)

async def save_video(fid: str, uid: int, fname: str):
    """Save video entry if not exists."""
    if videos.find_one({"file_id": fid}):
        return
    videos.insert_one({
        "file_id": fid,
        "user_id": uid,
        "file_name": fname,
        "uploaded_at": datetime.utcnow()
    })

def shorten_url_sync(long_url: str) -> str:
    """Sync shorten using AdrinoLinks (returns original URL on error)."""
    if not ADRINOLINKS_API_KEY:
        return long_url
    try:
        encoded = urllib.parse.quote(long_url, safe='')
        api = f"https://adrinolinks.in/api?api={ADRINOLINKS_API_KEY}&url={encoded}&format=text"
        r = requests.get(api, timeout=8)
        if r.status_code == 200:
            text = r.text.strip()
            if text.startswith("http"):
                return text
    except Exception as e:
        logger.warning(f"shorten_url_sync failed: {e}")
    return long_url

async def shorten_url(long_url: str) -> str:
    # keep blocking call but wrapped for clarity
    return shorten_url_sync(long_url)

# -------------------------
# START Command (deep link support)
# -------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    uid = message.from_user.id
    username = message.from_user.username

    # ensure user exists
    if not await get_user(uid):
        await create_user(uid, username)

    # deep-link param handling
    if len(message.command) > 1:
        param = message.command[1]

        # case 1: verify link (verify_<userid>), used to activate token
        if param.startswith("verify_"):
            # optional: check that verify_ matches same user or allow any
            # we simply activate for the current chatting user
            exp = await activate_token(uid)
            await message.reply_text(f"✅ Token activated! Valid until {exp.strftime('%d %b %Y %H:%M UTC')}. Use /upload.")
            return

        # case 2: base64 encoded get-<file_id> (URL-safe)
        try:
            # allow URL-safe base64; fix padding
            raw = param
            raw = raw.replace("-", "+").replace("_", "/")  # if someone used urlsafe incorrectly
            raw = _ensure_base64_padding(raw)
            decoded = base64.urlsafe_b64decode(raw).decode('utf-8')
        except Exception as e:
            logger.error(f"Base64 decode error for param={param}: {e}")
            # try fallback: plain param numeric (some old links may contain ids directly)
            try:
                decoded = param
            except:
                return await message.reply_text("❌ Invalid link data. Use /start for help.")

        # Expect decoded like "get-<file_id>" or maybe direct message id/file_id
        if isinstance(decoded, str) and decoded.startswith("get-"):
            file_id = decoded[len("get-"):]
            logger.info(f"user {uid} requested file_id {file_id} via deep link")

            # token check
            if not await is_token_valid(uid):
                # provide ad link to verify
                bot_username = (await client.get_me()).username
                verify_link = f"https://t.me/{bot_username}?start=verify_{uid}"
                short = await shorten_url(verify_link)
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📺 Watch Ad to Activate Token", url=short)]])
                return await message.reply_text(
                    "🎟️ Token required! Pehle ad dekhein aur token activate karein.",
                    reply_markup=keyboard
                )

            # fetch video record
            rec = videos.find_one({"file_id": file_id})
            if not rec:
                logger.warning(f"file_id {file_id} requested but not found in DB")
                return await message.reply_text("❌ Video not found (maybe deleted).")

            # send the video (file_id is Telegram file_id valid for send_video)
            try:
                await message.reply_text("📥 Fetching your video...")
                await client.send_video(chat_id=uid, video=file_id, caption="🎬 Here's your video")
                logger.info(f"Sent video {file_id} to {uid}")
            except Exception as exc:
                logger.error(f"Error sending video to {uid}: {exc}", exc_info=True)
                return await message.reply_text("❌ Video send failed (file may be expired/invalid).")
            return

        # else: other formats — ignore and continue to normal start flow

    # NORMAL start (no deep link or handled above)
    has_token = await is_token_valid(uid)
    if has_token:
        user = await get_user(uid)
        expires_at = user.get("token_expires_at")
        hrs_left = 0
        if expires_at:
            hrs_left = int((expires_at - datetime.utcnow()).total_seconds() // 3600)
        txt = (
            f"✅ Welcome back!\nToken active — ~{hrs_left}h left.\n\n"
            "Commands:\n/upload - (Admin) upload video\n/stats - your stats\n/help - help"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload", callback_data="upload"), InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ])
        return await message.reply_text(txt, reply_markup=kb)
    else:
        bot_username = (await client.get_me()).username
        verify_link = f"https://t.me/{bot_username}?start=verify_{uid}"
        short = await shorten_url(verify_link)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📺 Activate Token", url=short)]])
        return await message.reply_text(
            "👋 Welcome! Token inactive — watch ad to activate for 12 hours.",
            reply_markup=kb
        )

# -------------------------
# Upload / video handlers
# -------------------------
@app.on_message(filters.command("upload") & filters.private)
async def upload_command(client: Client, message: Message):
    uid = message.from_user.id
    if uid != ADMIN_ID:
        return await message.reply_text("❌ Sirf admin video upload kar sakta hai.")
    await message.reply_text("📤 Admin: Please send the video file now (MP4/MKV).")

@app.on_message(filters.video & filters.private)
async def handle_video(client: Client, message: Message):
    uid = message.from_user.id
    if uid != ADMIN_ID:
        return await message.reply_text("❌ Sirf admin video upload kar sakta hai.")

    processing = await message.reply_text("⏳ Processing video...")
    try:
        # forward to storage channel if configured, otherwise keep direct file_id
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

        # Save metadata
        await save_video(file_id, uid, message.video.file_name or "video.mp4")

        # Ensure uploader user exists and increment
        if not await get_user(uid):
            await create_user(uid, message.from_user.username)
        users.update_one({"user_id": uid}, {"$inc": {"videos_uploaded": 1}})

        # Create URL-safe base64 for sharing
        raw = f"get-{file_id}".encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")  # strip padding to make nicer link
        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded}"

        await processing.edit_text(
            f"✅ Video uploaded!\n\nShareable link:\n`{share_link}`\n\n"
            "Users who open this link will be shown an ad (if they don't have token) or will receive the video immediately if token is active."
        )
    except Exception as exc:
        logger.error(f"handle_video error: {exc}", exc_info=True)
        try:
            await processing.edit_text("❌ Error uploading video. Check logs.")
        except:
            pass

# -------------------------
# user commands: stats/help
# -------------------------
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    uid = message.from_user.id
    u = await get_user(uid)
    if not u:
        return await message.reply_text("❌ User record not found. Use /start first.")
    has = await is_token_valid(uid)
    token_text = "✅ Active" if has else "❌ Inactive"
    await message.reply_text(
        f"📊 Your Stats\n\n"
        f"👤 User ID: `{uid}`\n"
        f"🎟 Token Status: {token_text}\n"
        f"🎬 Videos uploaded: `{u.get('videos_uploaded', 0)}`\n"
        f"📅 Joined: {u['joined_at'].strftime('%d %b %Y')}"
    )

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    await message.reply_text(
        "❓ Help\n\n"
        "/start - Start the bot\n"
        "/upload - Admin only: upload video\n"
        "/stats - Your stats\n"
        "/help - This message\n\n"
        "Token: valid 12 hours; activate via the ad button."
    )

# -------------------------
# Callback handlers (inline buttons)
# -------------------------
@app.on_callback_query(filters.regex("^verify_token$"))
async def cb_verify_token(client: Client, cq: CallbackQuery):
    await cq.answer("Open the 'Activate Token' button (watch ad) to activate token.", show_alert=True)

@app.on_callback_query(filters.regex("^upload$"))
async def cb_upload(client: Client, cq: CallbackQuery):
    if cq.from_user.id != ADMIN_ID:
        await cq.answer("❌ Only admin can upload.", show_alert=True)
        return
    await cq.message.reply_text("📤 Admin: Please send the video now.")
    await cq.answer()

@app.on_callback_query(filters.regex("^stats$"))
async def cb_stats(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    u = await get_user(uid)
    if not u:
        return await cq.answer("User not found. Use /start.", show_alert=True)
    has = await is_token_valid(uid)
    await cq.answer(f"Token: {'✅ Active' if has else '❌ Inactive'}\nVideos: {u.get('videos_uploaded',0)}", show_alert=True)

# -------------------------
# Cleanup task
# -------------------------
async def cleanup_task():
    while True:
        try:
            res = users.update_many(
                {"token_expires_at": {"$lt": datetime.utcnow()}},
                {"$set": {"has_token": False, "token_expires_at": None}}
            )
            if getattr(res, "modified_count", 0):
                logger.info(f"Cleanup expired {res.modified_count} tokens")
        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)
        await asyncio.sleep(3600)

# -------------------------
# Admin broadcast / botstats
# -------------------------
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_command(client: Client, message: Message):
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply_text("Usage: /broadcast <text> or reply to a message to broadcast.")
    to_send = message.reply_to_message if message.reply_to_message else message.text.split(None,1)[1]
    total = succ = fail = 0
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

@app.on_message(filters.command("botstats") & filters.user(ADMIN_ID))
async def bot_stats_command(client: Client, message: Message):
    total_users = users.count_documents({})
    active_tokens = users.count_documents({"token_expires_at": {"$gt": datetime.utcnow()}})
    total_videos = videos.count_documents({})
    await message.reply_text(f"🤖 Bot Stats\n\nUsers: {total_users}\nActive tokens: {active_tokens}\nTotal videos: {total_videos}")

# -------------------------
# Health HTTP server (aiohttp)
# -------------------------
async def health(request):
    return web.Response(text="OK")

async def start_http_server():
    web_app = web.Application()
    web_app.router.add_get("/", health)
    web_app.router.add_get("/health", health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"HTTP server running on port {PORT}")

# -------------------------
# Main
# -------------------------
async def main():
    await app.start()
    logger.info("Bot started.")
    # background tasks
    asyncio.create_task(start_http_server())
    asyncio.create_task(cleanup_task())
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
