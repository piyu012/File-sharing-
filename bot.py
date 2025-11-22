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

# Validate configuration
if not os.getenv('ADRINOLINKS_API_KEY'):
    print("⚠️  Warning: ADRINOLINKS_API_KEY not set in .env file!")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
TOKEN_VALIDITY_HOURS = int(os.getenv('TOKEN_VALIDITY_HOURS', 12))
ADRINOLINKS_API_KEY = os.getenv('ADRINOLINKS_API_KEY')
STORAGE_CHANNEL_ID = int(os.getenv('STORAGE_CHANNEL_ID', 0))
PORT = int(os.getenv('PORT', 10000))

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

# Create indexes
users_collection.create_index("user_id", unique=True)
users_collection.create_index("token_expires_at")
videos_collection.create_index("file_id", unique=True)


# Helper Functions
async def get_user(user_id: int):
    """Get user from database"""
    return users_collection.find_one({"user_id": user_id})


async def create_user(user_id: int, username: str = None):
    """Create new user in database"""
    user_data = {
        "user_id": user_id,
        "username": username,
        "has_token": False,
        "token_expires_at": None,
        "last_ad_view": None,
        "videos_uploaded": 0,
        "joined_at": datetime.utcnow()
    }
    users_collection.insert_one(user_data)
    return user_data


async def is_token_valid(user_id: int):
    """Check if user's token is valid"""
    user = await get_user(user_id)
    if not user or not user.get('has_token'):
        return False
    
    expires_at = user.get('token_expires_at')
    if not expires_at:
        return False
    
    return datetime.utcnow() < expires_at


async def activate_token(user_id: int):
    """Activate token for user"""
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
    """Check if user needs to view ad"""
    user = await get_user(user_id)
    if not user:
        return True
    
    last_ad_view = user.get('last_ad_view')
    if not last_ad_view:
        return True
    
    # Check if 12 hours passed since last ad view
    return datetime.utcnow() - last_ad_view > timedelta(hours=TOKEN_VALIDITY_HOURS)


async def cleanup_expired_tokens():
    """Remove expired tokens automatically"""
    result = users_collection.update_many(
        {"token_expires_at": {"$lt": datetime.utcnow()}},
        {"$set": {"has_token": False, "token_expires_at": None}}
    )
    if result.modified_count > 0:
        logger.info(f"Cleaned up {result.modified_count} expired tokens")


async def save_video(file_id: str, user_id: int, file_name: str):
    """Save video to database"""
    video_data = {
        "file_id": file_id,
        "user_id": user_id,
        "file_name": file_name,
        "uploaded_at": datetime.utcnow()
    }
    videos_collection.insert_one(video_data)


async def shorten_url(long_url: str):
    """Shorten URL using AdrinoLinks API"""
    try:
        api_url = f"https://adrinolinks.in/api?api={ADRINOLINKS_API_KEY}&url={long_url}"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return data.get('shortenedUrl')
        return long_url
    except Exception as e:
        logger.error(f"URL shortening error: {e}")
        return long_url


# Command Handlers
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Create user if doesn't exist
    user = await get_user(user_id)
    if not user:
        await create_user(user_id, username)
    
    # Check token status
    has_valid_token = await is_token_valid(user_id)
    
    if has_valid_token:
        user = await get_user(user_id)
        expires_at = user['token_expires_at']
        time_left = expires_at - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        
        welcome_text = f"""
✅ **Welcome Back!**

🎟️ **Token Status:** Active
⏰ **Expires In:** {hours_left} hours

**Commands:**
📤 /upload - Upload video aur link generate karo
📊 /stats - Apne stats dekho
❓ /help - Help dekhein

**Video kaise upload karein:**
1. /upload command use karein
2. Video file send karein
3. Link milega jo aap share kar sakte ho!
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Video", callback_data="upload")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
        ])
    else:
        welcome_text = f"""
👋 **Welcome to Token Ad Bot!**

🎟️ **Token Status:** Inactive

Bot use karne ke liye token activate karein!

**Token Activation:**
Niche button click karke token activate karo - 12 hours valid rahega!

⚠️ **Note:** Video links automatically ad ke saath aayenge. User jab link open karega, pehle ad dekhega!
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Activate Token", callback_data="verify_token")]
        ])
    
    await message.reply_text(welcome_text, reply_markup=keyboard)


@app.on_message(filters.command("upload") & filters.private)
async def upload_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if user needs to view ad
    if await needs_ad_view(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_token")]
        ])
        
        await message.reply_text(
            "⏰ **12 hours ho gaye!**\n\n"
            "Bot continue use karne ke liye ad dekhein aur verify karein.",
            reply_markup=keyboard
        )
        return
    
    # Check token validity
    if not await is_token_valid(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad & Get Token", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify Token", callback_data="verify_token")]
        ])
        
        await message.reply_text(
            "❌ **Token Expired!**\n\n"
            "Pehle token activate karein.",
            reply_markup=keyboard
        )
        return
    
    await message.reply_text(
        "📤 **Upload your video:**\n\n"
        "Video file send karein (MP4, MKV, etc.)\n"
        "Max size: 2GB"
    )


@app.on_message(filters.video & filters.private)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check token
    if not await is_token_valid(user_id):
        await message.reply_text("❌ Token invalid! Pehle /start use karein.")
        return
    
    # Check if needs ad view
    if await needs_ad_view(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 View Ad", url=AD_URL)],
            [InlineKeyboardButton("✅ Verify", callback_data="verify_token")]
        ])
        await message.reply_text(
            "⏰ 12 hours complete! Ad dekhein.",
            reply_markup=keyboard
        )
        return
    
    processing_msg = await message.reply_text("⏳ Processing video...")
    
    try:
        # Forward to storage channel if configured
        if STORAGE_CHANNEL_ID:
            stored_msg = await message.forward(STORAGE_CHANNEL_ID)
            file_id = stored_msg.video.file_id
        else:
            file_id = message.video.file_id
        
        # Save to database
        await save_video(
            file_id,
            user_id,
            message.video.file_name or "video.mp4"
        )
        
        # Update user stats
        users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"videos_uploaded": 1}}
        )
        
        # Generate shareable link
        bot_username = (await client.get_me()).username
        video_link = f"https://t.me/{bot_username}?start=video_{file_id}"
        
        # Shorten link with AdrinoLinks
        short_link = await shorten_url(video_link)
        
        success_text = f"""
✅ **Video uploaded successfully!**

📎 **Shareable Link (with Ad):**
`{short_link}`

**Link ko copy karke share karein!**
**User ko pehle ad dikhega, phir video access milega**

📊 Total videos: {(await get_user(user_id))['videos_uploaded']}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Another", callback_data="upload")]
        ])
        
        await processing_msg.edit_text(success_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await processing_msg.edit_text("❌ Error uploading video. Try again.")


@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.reply_text("❌ User not found. Use /start first.")
        return
    
    has_valid_token = await is_token_valid(user_id)
    
    if has_valid_token:
        expires_at = user['token_expires_at']
        time_left = expires_at - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        token_status = f"✅ Active ({hours_left}h left)"
    else:
        token_status = "❌ Inactive"
    
    stats_text = f"""
📊 **Your Statistics**

👤 **User ID:** `{user_id}`
🎟️ **Token Status:** {token_status}
📤 **Videos Uploaded:** {user['videos_uploaded']}
📅 **Joined:** {user['joined_at'].strftime('%d %b %Y')}
"""
    
    await message.reply_text(stats_text)


@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    help_text = """
❓ **Help & Commands**

**Basic Commands:**
/start - Bot start karein
/upload - Video upload karein
/stats - Apne stats dekho
/help - Ye message

**Token System:**
• Token har 12 ghante valid rehta hai
• Renew karne ke liye ad dekhna mandatory hai
• Bina token ke bot use nahi kar sakte

**Video Upload:**
1. /upload command use karein
2. Video file send karein (max 2GB)
3. Shareable link milega

**Questions?**
Contact admin for support.
"""
    
    await message.reply_text(help_text)


# Callback Query Handlers
@app.on_callback_query(filters.regex("^verify_token$"))
async def verify_token_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Activate token
    expires_at = await activate_token(user_id)
    
    success_text = f"""
✅ **Token Activated Successfully!**

⏰ **Valid Until:** {expires_at.strftime('%d %b %Y, %I:%M %p')} UTC
⏳ **Duration:** {TOKEN_VALIDITY_HOURS} hours

Ab aap bot use kar sakte ho!

**Commands:**
📤 /upload - Video upload karein
📊 /stats - Stats dekhein
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Video", callback_data="upload")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
    ])
    
    await callback_query.message.edit_text(success_text, reply_markup=keyboard)
    await callback_query.answer("✅ Token activated!", show_alert=True)


@app.on_callback_query(filters.regex("^upload$"))
async def upload_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.reply_text(
        "📤 **Upload your video:**\n\n"
        "Video file send karein (MP4, MKV, etc.)"
    )
    await callback_query.answer()


@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user = await get_user(user_id)
    
    has_valid_token = await is_token_valid(user_id)
    
    if has_valid_token:
        expires_at = user['token_expires_at']
        time_left = expires_at - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        token_status = f"✅ Active ({hours_left}h left)"
    else:
        token_status = "❌ Inactive"
    
    stats_text = f"""
📊 **Your Statistics**

🎟️ **Token:** {token_status}
📤 **Videos:** {user['videos_uploaded']}
📅 **Joined:** {user['joined_at'].strftime('%d %b %Y')}
"""
    
    await callback_query.answer(stats_text, show_alert=True)


# Background task for cleaning expired tokens
async def cleanup_task():
    while True:
        try:
            await cleanup_expired_tokens()
            await asyncio.sleep(3600)  # Run every hour
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
            await asyncio.sleep(300)  # Retry after 5 minutes


# Admin Commands
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return
    
    broadcast_text = message.text.split(None, 1)[1]
    users = users_collection.find()
    
    success = 0
    failed = 0
    
    status_msg = await message.reply_text("📡 Broadcasting...")
    
    for user in users:
        try:
            await client.send_message(user['user_id'], broadcast_text)
            success += 1
        except:
            failed += 1
    
    await status_msg.edit_text(
        f"✅ Broadcast complete!\n\n"
        f"Success: {success}\nFailed: {failed}"
    )


@app.on_message(filters.command("botstats") & filters.user(ADMIN_ID))
async def bot_stats_command(client: Client, message: Message):
    total_users = users_collection.count_documents({})
    active_tokens = users_collection.count_documents({
        "token_expires_at": {"$gt": datetime.utcnow()}
    })
    total_videos = videos_collection.count_documents({})
    
    stats_text = f"""
🤖 **Bot Statistics**

👥 **Total Users:** {total_users}
✅ **Active Tokens:** {active_tokens}
🎬 **Total Videos:** {total_videos}
📅 **Uptime:** Running smoothly
"""
    
    await message.reply_text(stats_text)


# HTTP server for Render health check
async def health_check(request):
    return web.Response(text="Bot is running!")


async def start_http_server():
    """Start HTTP server for Render port binding"""
    app_web = web.Application()
    app_web.router.add_get('/health', health_check)
    app_web.router.add_get('/', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"HTTP server started on port {PORT}")


# Main function
async def main():
    await app.start()
    logger.info("Bot started successfully!")
    
    # Start HTTP server for Render
    asyncio.create_task(start_http_server())
    
    # Start cleanup task
    asyncio.create_task(cleanup_task())
    
    await asyncio.Event().wait()


if __name__ == "__main__":
    app.run(main())
