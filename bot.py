# token_ad_bot_fixed.py
import os
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration (provide safe defaults where possible)
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MONGODB_URI = os.getenv('MONGODB_URI', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
TOKEN_VALIDITY_HOURS = int(os.getenv('TOKEN_VALIDITY_HOURS', 12))
AD_URL = os.getenv('AD_URL', 'https://example.com/ad')
STORAGE_CHANNEL_ID = int(os.getenv('STORAGE_CHANNEL_ID', 0))

# Validate critical config early
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set. Exiting.")
    raise SystemExit(1)
if not MONGODB_URI:
    logger.error("MONGODB_URI not set. Exiting.")
    raise SystemExit(1)

# Initialize Pyrogram Client
app = Client(
    "token_ad_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# MongoDB Setup (synchronous pymongo)
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client['telegram_bot']
users_collection = db['users']
videos_collection = db['videos']

# Create indexes (safe to call repeatedly)
try:
    users_collection.create_index("user_id", unique=True)
    users_collection.create_index("token_expires_at")
    videos_collection.create_index("file_id", unique=True)
except Exception as e:
    logger.warning(f"Index creation warning: {e}")

# Helper Functions (they are async so you can 'await' them in handlers)
async def get_user(user_id: int):
    """Return user document or None."""
    try:
        return users_collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"DB get_user error: {e}")
        return None

async def create_user(user_id: int, username: str = None):
    """Create new user document (no-op if exists)."""
    now = datetime.utcnow()
    user_data = {
        "user_id": user_id,
        "username": username,
        "has_token": False,
        "token_expires_at": None,
        "last_ad_view": None,
        "videos_uploaded": 0,
        "joined_at": now
    }
    try:
        users_collection.update_one({"user_id": user_id}, {"$setOnInsert": user_data}, upsert=True)
        return users_collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"DB create_user error: {e}")
        return None

async def is_token_valid(user_id: int) -> bool:
    """Return True if token exists and not expired."""
    user = await get_user(user_id)
    if not user or not user.get("has_token"):
        return False
    expires_at = user.get("token_expires_at")
    if not isinstance(expires_at, datetime):
        return False
    return datetime.utcnow() < expires_at

async def activate_token(user_id: int):
    """Activate token: set has_token True and token_expires_at."""
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_VALIDITY_HOURS)
    try:
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "has_token": True,
                "token_expires_at": expires_at,
                "last_ad_view": datetime.utcnow()
            }},
            upsert=True
        )
        return expires_at
    except Exception as e:
        logger.error(f"activate_token error: {e}")
        return None

async def needs_ad_view(user_id: int) -> bool:
    """Return True if user needs to view ad before continuing."""
    user = await get_user(user_id)
    if not user:
        return True
    last = user.get("last_ad_view")
    if not isinstance(last, datetime):
        return True
    return (datetime.utcnow() - last) > timedelta(hours=TOKEN_VALIDITY_HOURS)

async def cleanup_expired_tokens():
    """Reset has_token for expired tokens."""
    try:
        result = users_collection.update_many(
            {"token_expires_at": {"$lt": datetime.utcnow()}},
            {"$set": {"has_token": False, "token_expires_at": None}}
        )
        if result.modified_count:
            logger.info(f"Cleaned up {result.modified_count} expired tokens")
    except Exception as e:
        logger.error(f"cleanup_expired_tokens error: {e}")

async def save_video(file_id: str, user_id: int, file_name: str):
    """Save video metadata to DB."""
    try:
        videos_collection.insert_one({
            "file_id": file_id,
            "user_id": user_id,
            "file_name": file_name,
            "uploaded_at": datetime.utcnow()
        })
    except Exception as e:
        logger.error(f"save_video error: {e}")

# -----------------------
# START COMMAND
# -----------------------
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    # Ensure user exists in DB
    user = await get_user(user_id)
    if not user:
        user = await create_user(user_id, username)

    # Check if token currently valid
    valid = await is_token_valid(user_id)

    if valid:
        user = await get_user(user_id)  # fresh
        expires_at = user.get("token_expires_at")
        # safe compute remaining time
        if isinstance(expires_at, datetime):
            seconds_left = max(0, int((expires_at - datetime.utcnow()).total_seconds()))
            hours_left = seconds_left // 3600
            minutes_left = (seconds_left % 3600) // 60
            expires_str = f"{hours_left}h {minutes_left}m"
        else:
            expires_str = "unknown"

        welcome_text = (
            "✅ *Welcome Back!*\n\n"
            f"🎟️ *Token Status:* Active\n"
            f"⏰ *Expires In:* {expires_str}\n\n"
            "*Commands:*\n"
            "📤 /upload - Upload video and generate link\n"
            "📊 /stats - View your stats\n"
            "❓ /help - Show help\n\n"
            "*How to upload video:*\n"
            "1. Send /upload\n"
            "2. Send your video file\n"
            "3. Get shareable link\n"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Video", callback_data="upload")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
        ])

        await message.reply_text(welcome_text, reply_markup=keyboard)
        return

    # If not valid -> prompt to view ad + verify
    welcome_text = (
        "👋 *Welcome to Token Ad Bot!*\n\n"
        "🎟️ *Token Status:* Inactive\n\n"
        "To use the bot you must activate a token.\n\n"
        "*Token Activation Steps:*\n"
        "1. Click 'View Ad' below\n"
        "2. Keep the ad page open for ~10 seconds\n"
        "3. Come back and press 'Verify Token'\n"
        "4. Token will be valid for 12 hours\n\n"
        "⚠️ Token expires after 12 hours; watch ad again to renew."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 View Ad & Get Token", url=AD_URL)],
        [InlineKeyboardButton("✅ Verify Token", callback_data="verify_token")]
    ])
    await message.reply_text(welcome_text, reply_markup=keyboard)

# -----------------------
# UPLOAD COMMAND
# -----------------------
@app.on_message(filters.command("upload") & filters.private)
async def upload_command(client: Client, message: Message):
    user_id = message.from_user.id

    if await needs_ad_view(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_token")]
        ])
        await message.reply_text(
            "⏰ Your token needs renewal. Watch the ad and verify to continue.",
            reply_markup=keyboard
        )
        return

    if not await is_token_valid(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad & Get Token", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify Token", callback_data="verify_token")]
        ])
        await message.reply_text(
            "❌ Token expired. Please activate token first.",
            reply_markup=keyboard
        )
        return

    await message.reply_text(
        "📤 *Upload your video:*\n\n"
        "Send the video file (MP4, MKV, etc.). Max size: 2GB"
    )

# -----------------------
# VIDEO HANDLER
# -----------------------
@app.on_message(filters.video & filters.private)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id

    if not await is_token_valid(user_id):
        await message.reply_text("❌ Token invalid! Please run /start.")
        return

    if await needs_ad_view(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify", callback_data="verify_token")]
        ])
        await message.reply_text("⏰ 12 hours passed — please view ad and verify.", reply_markup=keyboard)
        return

    processing_msg = await message.reply_text("⏳ Processing video...")
    try:
        # store video to channel if configured
        if STORAGE_CHANNEL_ID:
            stored_msg = await message.forward(STORAGE_CHANNEL_ID)
            file_id = stored_msg.video.file_id
        else:
            file_id = message.video.file_id

        await save_video(file_id, user_id, message.video.file_name or "video")

        users_collection.update_one({"user_id": user_id}, {"$inc": {"videos_uploaded": 1}})

        bot_username = (await client.get_me()).username or ""
        video_link = f"https://t.me/{bot_username}?start=video_{file_id}"

        success_text = (
            "✅ *Video uploaded successfully!*\n\n"
            f"📎 Shareable Link:\n`{video_link}`\n\n"
            f"📊 Total videos: {get_user_sync_count(user_id)}"
        )

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Upload Another", callback_data="upload")]])
        await processing_msg.edit_text(success_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await processing_msg.edit_text("❌ Error uploading video. Try again later.")

# small helper to get updated video count synchronously for display (safe)
def get_user_sync_count(user_id: int) -> int:
    try:
        u = users_collection.find_one({"user_id": user_id})
        return int(u.get("videos_uploaded", 0)) if u else 0
    except:
        return 0

# -----------------------
# STATS & HELP
# -----------------------
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        return await message.reply_text("❌ User not found. Use /start first.")

    valid = await is_token_valid(user_id)
    if valid:
        expires_at = user.get("token_expires_at")
        seconds_left = max(0, int((expires_at - datetime.utcnow()).total_seconds())) if isinstance(expires_at, datetime) else 0
        hours_left = seconds_left // 3600
        token_status = f"✅ Active ({hours_left}h left)"
    else:
        token_status = "❌ Inactive"

    stats_text = (
        "📊 *Your Statistics*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"🎟️ Token Status: {token_status}\n"
        f"📤 Videos Uploaded: {user.get('videos_uploaded', 0)}\n"
        f"📅 Joined: {user.get('joined_at').strftime('%d %b %Y') if isinstance(user.get('joined_at'), datetime) else 'unknown'}\n"
    )
    await message.reply_text(stats_text)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    help_text = (
        "❓ *Help & Commands*\n\n"
        "/start - Start the bot\n"
        "/upload - Upload a video\n"
        "/stats - Your stats\n"
        "/help - This help\n\n"
        "Token system: token valid for 12h, renew by viewing ad."
    )
    await message.reply_text(help_text)

# -----------------------
# CALLBACKS
# -----------------------
@app.on_callback_query(filters.regex("^verify_token$"))
async def verify_token_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    expires_at = await activate_token(user_id)
    if not expires_at:
        await callback_query.answer("Token activation failed.", show_alert=True)
        return

    success_text = (
        "✅ *Token Activated Successfully!*\n\n"
        f"⏰ Valid Until: {expires_at.strftime('%d %b %Y, %I:%M %p')} UTC\n"
        f"⏳ Duration: {TOKEN_VALIDITY_HOURS} hours\n\n"
        "Now you can use the bot.\n"
        "Commands: /upload, /stats"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Video", callback_data="upload")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
    ])
    await callback_query.message.edit_text(success_text, reply_markup=keyboard)
    await callback_query.answer("✅ Token activated!", show_alert=True)

@app.on_callback_query(filters.regex("^upload$"))
async def upload_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.reply_text("📤 Upload: send your video file (MP4, MKV, etc.)")
    await callback_query.answer()

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user = await get_user(user_id)
    if not user:
        await callback_query.answer("User not found.", show_alert=True)
        return

    valid = await is_token_valid(user_id)
    if valid:
        expires_at = user.get("token_expires_at")
        seconds_left = max(0, int((expires_at - datetime.utcnow()).total_seconds())) if isinstance(expires_at, datetime) else 0
        hours_left = seconds_left // 3600
        token_status = f"✅ Active ({hours_left}h left)"
    else:
        token_status = "❌ Inactive"

    stats_text = (
        "📊 *Your Statistics*\n\n"
        f"🎟️ Token: {token_status}\n"
        f"📤 Videos: {user.get('videos_uploaded', 0)}\n"
        f"📅 Joined: {user.get('joined_at').strftime('%d %b %Y') if isinstance(user.get('joined_at'), datetime) else 'unknown'}"
    )
    await callback_query.answer(stats_text, show_alert=True)

# -----------------------
# BACKGROUND CLEANUP TASK
# -----------------------
async def cleanup_task():
    while True:
        try:
            await cleanup_expired_tokens()
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
            await asyncio.sleep(300)

# -----------------------
# ADMIN COMMANDS
# -----------------------
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return
    broadcast_text = message.text.split(None, 1)[1]
    users = users_collection.find()
    success = failed = 0
    status_msg = await message.reply_text("📡 Broadcasting...")
    for u in users:
        try:
            await client.send_message(u['user_id'], broadcast_text)
            success += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ Broadcast complete!\nSuccess: {success}\nFailed: {failed}")

@app.on_message(filters.command("botstats") & filters.user(ADMIN_ID))
async def bot_stats_command(client: Client, message: Message):
    total_users = users_collection.count_documents({})
    active_tokens = users_collection.count_documents({"token_expires_at": {"$gt": datetime.utcnow()}})
    total_videos = videos_collection.count_documents({})
    stats_text = (
        "🤖 *Bot Statistics*\n\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Active Tokens: {active_tokens}\n"
        f"🎬 Total Videos: {total_videos}\n"
    )
    await message.reply_text(stats_text)

# -----------------------
# STARTUP
# -----------------------
async def main():
    await app.start()
    logger.info("Bot started successfully!")
    # start cleanup background task
    asyncio.create_task(cleanup_task())
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
