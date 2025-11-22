# bot.py (fixed)
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

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration (with safe defaults)
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
TOKEN_VALIDITY_HOURS = int(os.getenv('TOKEN_VALIDITY_HOURS', '12'))
ADRINOLINKS_API_KEY = os.getenv('ADRINOLINKS_API_KEY', None)
STORAGE_CHANNEL_ID = int(os.getenv('STORAGE_CHANNEL_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))
# AD_URL used as fallback (you can set this to your ad landing page)
AD_URL = os.getenv('AD_URL', 'https://example.com/ad')

# Initialize Pyrogram Client
app = Client(
    "token_ad_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# MongoDB Setup
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client['telegram_bot']
users_collection = db['users']
videos_collection = db['videos']

# Create indexes (idempotent)
try:
    users_collection.create_index("user_id", unique=True)
    users_collection.create_index("token_expires_at")
    videos_collection.create_index("file_id", unique=True)
except Exception as e:
    logger.warning(f"Index creation warning: {e}")

# ---------------------------
# Helper Functions (sync mongo used inside async functions)
# ---------------------------
async def get_user(user_id: int):
    """Get user from database"""
    return users_collection.find_one({"user_id": user_id})


async def create_user(user_id: int, username: str = None):
    """Create or ensure user exists (upsert)"""
    now = datetime.utcnow()
    users_collection.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "username": username,
            "has_token": False,
            "token_expires_at": None,
            "last_ad_view": None,
            "videos_uploaded": 0,
            "joined_at": now
        }},
        upsert=True
    )
    return users_collection.find_one({"user_id": user_id})


async def is_token_valid(user_id: int):
    """Check if user's token is valid"""
    user = await get_user(user_id)
    if not user or not user.get('has_token'):
        return False
    expires_at = user.get('token_expires_at')
    if not expires_at:
        return False
    # expires_at stored as datetime
    return datetime.utcnow() < expires_at


async def activate_token(user_id: int):
    """Activate token for user and return expiry datetime"""
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_VALIDITY_HOURS)
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "has_token": True,
            "token_expires_at": expires_at,
            "last_ad_view": datetime.utcnow()
        }}
    )
    return expires_at


async def needs_ad_view(user_id: int):
    """Return True if user needs to view ad (no last view or expired)"""
    user = await get_user(user_id)
    if not user:
        return True
    last_ad_view = user.get('last_ad_view')
    if not last_ad_view:
        return True
    return datetime.utcnow() - last_ad_view > timedelta(hours=TOKEN_VALIDITY_HOURS)


async def cleanup_expired_tokens():
    """Expire tokens whose expiry passed"""
    result = users_collection.update_many(
        {"token_expires_at": {"$lt": datetime.utcnow()}},
        {"$set": {"has_token": False, "token_expires_at": None}}
    )
    if getattr(result, "modified_count", 0) > 0:
        logger.info(f"Cleaned up {result.modified_count} expired tokens")


async def save_video(file_id: str, user_id: int, file_name: str):
    """Save video to DB if not present"""
    existing = videos_collection.find_one({"file_id": file_id})
    if existing:
        logger.info(f"Video already exists: {file_id}")
        return
    video_data = {
        "file_id": file_id,
        "user_id": user_id,
        "file_name": file_name,
        "uploaded_at": datetime.utcnow()
    }
    videos_collection.insert_one(video_data)
    logger.info(f"Video saved: {file_id}")


def shorten_url_sync(long_url: str):
    """Synchronous URL shortener using AdrinoLinks (returns original on failure)"""
    if not ADRINOLINKS_API_KEY:
        return long_url
    try:
        import urllib.parse
        encoded_url = urllib.parse.quote(long_url, safe='')
        api_url = f"https://adrinolinks.in/api?api={ADRINOLINKS_API_KEY}&url={encoded_url}&format=text"
        resp = requests.get(api_url, timeout=10)
        if resp.status_code == 200:
            short = resp.text.strip()
            if short.startswith("http"):
                return short
    except Exception as e:
        logger.warning(f"Shorten URL failed: {e}")
    return long_url


async def shorten_url(long_url: str):
    # run sync shortener in thread to avoid blocking if needed
    return shorten_url_sync(long_url)


# ---------------------------
# Command handlers
# ---------------------------

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    # create or ensure user exists
    await create_user(user_id, username)

    # handle deep link parameters
    try:
        if len(message.command) > 1:
            param = message.command[1]
            logger.info(f"Deep-link param for {user_id}: {param}")

            # case 1: token verification callback
            if param.startswith("verify_"):
                # activate token for that user id (if admin or same user)
                # verify_{user_id} is our format
                try:
                    # optionally check that param ends with user id, but we allow activation for the caller
                    expires_at = await activate_token(user_id)
                    await message.reply_text(
                        f"✅ Token activated! Valid until {expires_at.strftime('%d %b %Y %H:%M:%S')} UTC\n"
                        "Use /upload to upload videos or open your link again."
                    )
                except Exception as e:
                    logger.error(f"Token activation error: {e}")
                    await message.reply_text("❌ Token activation failed. Try again.")
                return

            # case 2: encoded get-<file_id> deep link (base64)
            # allow both urlsafe base64 and plain base64 (no padding)
            import base64 as _b64

            param_for_decode = param
            # fix urlsafe to normal base64 if necessary
            # add padding
            missing_padding = len(param_for_decode) % 4
            if missing_padding:
                param_for_decode += '=' * (4 - missing_padding)

            try:
                decoded = _b64.b64decode(param_for_decode).decode('utf-8')
            except Exception:
                # try urlsafe decode
                try:
                    decoded = _b64.urlsafe_b64decode(param_for_decode).decode('utf-8')
                except Exception as e:
                    logger.error(f"Deep-link decode failed for {param}: {e}")
                    decoded = None

            if decoded:
                logger.info(f"Decoded deep-link for {user_id}: {decoded}")
                if decoded.startswith("get-"):
                    file_id = decoded[len("get-"):]
                    # token check
                    if not await is_token_valid(user_id):
                        # provide ad & verify flow
                        bot_username = (await client.get_me()).username
                        verify_link = f"https://t.me/{bot_username}?start=verify_{user_id}"
                        ad_link = await shorten_url(verify_link) or AD_URL
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📺 View Ad to Activate Token", url=ad_link)]
                        ])
                        await message.reply_text(
                            "🎟️ **Token Required!**\n\n"
                            "To view this video, please watch the ad and activate token.",
                            reply_markup=keyboard
                        )
                        return

                    # find video in DB
                    video = videos_collection.find_one({"file_id": file_id})
                    if video:
                        await message.reply_text("📥 Fetching your video...")
                        try:
                            await client.send_video(user_id, file_id, caption="🎬 Here's your video!")
                            logger.info(f"Sent video {file_id} to {user_id}")
                        except Exception as e:
                            logger.error(f"Error sending video {file_id} to {user_id}: {e}")
                            await message.reply_text("❌ Could not send video. Possibly invalid file id.")
                    else:
                        await message.reply_text("❌ Video not found in database.")
                    return

    except Exception as e:
        logger.error(f"Error in deep link handling: {e}")
        # continue to send welcome text

    # normal /start welcome message
    has_valid_token = await is_token_valid(user_id)
    if has_valid_token:
        user = await get_user(user_id)
        expires_at = user.get('token_expires_at')
        hours_left = 0
        if expires_at:
            hours_left = int((expires_at - datetime.utcnow()).total_seconds() // 3600)
        welcome_text = (
            "✅ Welcome back!\n\n"
            f"🎟️ Token status: Active (≈ {hours_left} hours remaining)\n\n"
            "Commands:\n"
            "/upload - Upload video\n"
            "/stats - Your stats\n"
            "/help - Help\n"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Video", callback_data="upload")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
        ])
    else:
        # provide ad link to activate token
        bot_username = (await client.get_me()).username
        verify_link = f"https://t.me/{bot_username}?start=verify_{user_id}"
        ad_link = await shorten_url(verify_link) or AD_URL
        welcome_text = (
            "👋 Welcome to Token Ad Bot!\n\n"
            "🎟️ Token status: Inactive\n\n"
            "To use the bot, view the ad and activate the token (valid for 12 hours)."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad to Activate Token", url=ad_link)]
        ])

    await message.reply_text(welcome_text, reply_markup=keyboard)


@app.on_message(filters.command("upload") & filters.private)
async def upload_command(client: Client, message: Message):
    user_id = message.from_user.id

    # Only admin allowed to upload in this implementation (as per your original)
    if user_id != ADMIN_ID:
        await message.reply_text("❌ Only admin can upload videos.")
        return

    # token check not strictly necessary for admin, but keep consistent
    if await needs_ad_view(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_token")]
        ])
        await message.reply_text("Please view the ad and verify to continue.", reply_markup=keyboard)
        return

    await message.reply_text("📤 Send me the video file now (max size depends on bot limits).")


@app.on_message(filters.video & filters.private)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id

    # Only admin may upload
    if user_id != ADMIN_ID:
        await message.reply_text("❌ Only admin can upload videos.")
        return

    # ensure admin has token (optional)
    if not await is_token_valid(user_id):
        await message.reply_text("❌ Your token is not active. Activate it first.")
        return

    processing_msg = await message.reply_text("⏳ Processing video...")

    try:
        # forward to storage channel (preferred) or fallback to direct file_id
        if STORAGE_CHANNEL_ID and STORAGE_CHANNEL_ID != 0:
            try:
                stored_msg = await message.forward(STORAGE_CHANNEL_ID)
                # depending on type may be stored_msg.video or stored_msg.document
                if getattr(stored_msg, "video", None):
                    file_id = stored_msg.video.file_id
                elif getattr(stored_msg, "document", None):
                    file_id = stored_msg.document.file_id
                else:
                    file_id = message.video.file_id
                logger.info(f"Forwarded to storage channel, file_id={file_id}")
            except Exception as forward_err:
                logger.error(f"Forward to storage failed: {forward_err}")
                file_id = message.video.file_id
                logger.info("Using direct file_id fallback")
        else:
            file_id = message.video.file_id

        # save in DB
        await save_video(file_id, user_id, message.video.file_name or "video.mp4")

        # increment user uploads counter (admin user's stats)
        users_collection.update_one({"user_id": user_id}, {"$inc": {"videos_uploaded": 1}})

        # prepare shareable base64 link
        import base64 as _b64
        encoded_id = _b64.b64encode(f"get-{file_id}".encode()).decode()
        bot_username = (await client.get_me()).username
        video_link = f"https://t.me/{bot_username}?start={encoded_id}"

        success_text = (
            "✅ Video uploaded successfully!\n\n"
            f"📎 Shareable Link:\n`{video_link}`\n\n"
            "Share this link — when a user opens it, they will be asked to view an ad if their token is inactive."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Upload Another", callback_data="upload")]])
        await processing_msg.edit_text(success_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)
        await processing_msg.edit_text("❌ Error uploading video. Try again later.")


@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        await message.reply_text("❌ User not found. Use /start first.")
        return

    has_valid = await is_token_valid(user_id)
    token_status = "✅ Active" if has_valid else "❌ Inactive"
    uploaded = user.get("videos_uploaded", 0)
    joined = user.get("joined_at")
    joined_str = joined.strftime("%d %b %Y") if joined else "N/A"

    stats_text = (
        f"📊 Your Statistics\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"🎟️ Token Status: {token_status}\n"
        f"📤 Videos Uploaded: `{uploaded}`\n"
        f"📅 Joined: {joined_str}\n"
    )
    await message.reply_text(stats_text)


@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    help_text = (
        "❓ Help & Commands\n\n"
        "/start - Start bot / open deep link\n"
        "/upload - Upload (admin only)\n"
        "/stats - Your stats\n"
        "/help - This message\n\n"
        "Token system: token valid for 12 hours. View ad -> click verify link to activate."
    )
    await message.reply_text(help_text)


# Callback handlers (verify_token, upload, stats)
@app.on_callback_query(filters.regex("^verify_token$"))
async def verify_token_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        expires_at = await activate_token(user_id)
        await callback_query.answer("✅ Token activated!", show_alert=True)
        await callback_query.message.edit_text(
            f"✅ Token activated! Valid until {expires_at.strftime('%d %b %Y %H:%M:%S')} UTC"
        )
    except Exception as e:
        logger.error(f"verify_token callback failed: {e}")
        await callback_query.answer("❌ Activation failed", show_alert=True)


@app.on_callback_query(filters.regex("^upload$"))
async def upload_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.reply_text("📤 Send the video file now.")
    await callback_query.answer()


@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user = await get_user(user_id)
    if not user:
        await callback_query.answer("User not found", show_alert=True)
        return
    has_valid = await is_token_valid(user_id)
    token_status = "✅ Active" if has_valid else "❌ Inactive"
    await callback_query.answer(f"Token: {token_status}\nVideos: {user.get('videos_uploaded',0)}", show_alert=True)


# Background cleanup task
async def cleanup_task():
    while True:
        try:
            await cleanup_expired_tokens()
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
        await asyncio.sleep(3600)


# Admin commands: broadcast & botstats
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return
    text = message.text.split(None, 1)[1]
    users = users_collection.find({}, {"user_id": 1})
    success = failed = 0
    status = await message.reply_text("📡 Broadcasting...")
    for u in users:
        try:
            await client.send_message(u['user_id'], text)
            success += 1
        except Exception:
            failed += 1
    await status.edit_text(f"✅ Broadcast complete!\nSuccess: {success}\nFailed: {failed}")


@app.on_message(filters.command("botstats") & filters.user(ADMIN_ID))
async def bot_stats_command(client: Client, message: Message):
    total_users = users_collection.count_documents({})
    active_tokens = users_collection.count_documents({"token_expires_at": {"$gt": datetime.utcnow()}})
    total_videos = videos_collection.count_documents({})
    await message.reply_text(
        f"🤖 Bot Statistics\n\nUsers: {total_users}\nActive tokens: {active_tokens}\nVideos: {total_videos}"
    )


# HTTP server for health checks (Render / other)
async def health_check(request):
    return web.Response(text="Bot is running!")


async def start_http_server():
    app_web = web.Application()
    app_web.router.add_get('/health', health_check)
    app_web.router.add_get('/', health_check)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"HTTP server started on port {PORT}")


# Main
async def main():
    await app.start()
    logger.info("Bot started")
    # start tasks
    asyncio.create_task(start_http_server())
    asyncio.create_task(cleanup_task())
    # keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
