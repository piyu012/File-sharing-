# File Sharing Bot - Complete Single File Implementation
# Updated and cleaned version

import os
import sys
import time
import asyncio
import datetime
import logging
import base64
from typing import Tuple

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant

from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

class Config:
    API_HASH = os.environ.get("API_HASH", "")
    APP_ID = int(os.environ.get("APP_ID", "0"))
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    
    DB_URL = os.environ.get("DB_URL", "")
    DB_NAME = os.environ.get("DB_NAME", "FileSharingBot")
    
    PORT = int(os.environ.get("PORT", "10000"))
    
    PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False").lower() == "true"
    FILE_AUTO_DELETE = int(os.environ.get("FILE_AUTO_DELETE", "600"))
    
    ADMINS = [OWNER_ID]
    admin_list = os.environ.get("ADMINS", "")
    if admin_list:
        ADMINS.extend([int(x) for x in admin_list.split()])
    
    FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "0")
    if FORCE_SUB_CHANNEL != "0":
        try:
            FORCE_SUB_CHANNEL = int(FORCE_SUB_CHANNEL)
        except:
            FORCE_SUB_CHANNEL = str(FORCE_SUB_CHANNEL)
    
    START_MESSAGE = os.environ.get("START_MESSAGE", "<b>Hello {mention}!\nI'm a File Sharing Bot.</b>")
    FORCE_SUB_MESSAGE = os.environ.get("FORCE_SUB_MESSAGE", "<b>Join @{channel} first!</b>")
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "")
    DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False").lower() == "true"
    BOT_STATS_TEXT = os.environ.get("BOT_STATS_TEXT", "<b>Bot Uptime: {uptime}\nUsers: {users}\nFiles: {files}</b>")
    USER_REPLY_TEXT = os.environ.get("USER_REPLY_TEXT", "<b>Invalid command! Use /start</b>")

# ============================================
# HEALTH CHECK SERVER
# ============================================

async def health_check(request):
    return web.Response(text="Bot is running! ✅", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Health server started on port {Config.PORT}")

# ============================================
# DATABASE
# ============================================

class Database:
    def __init__(self, uri, db_name):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.users = self.db['users']
        self.files = self.db['files']

    async def add_user(self, user_id, first_name, username):
        try:
            await self.users.update_one(
                {'id': user_id},
                {'$set': {'id': user_id, 'first_name': first_name, 'username': username, 'join_date': datetime.datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Add user error: {e}")

    async def get_all_users(self):
        return await self.users.find().to_list(length=None)

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def add_file(self, file_id, unique_id, caption=None):
        try:
            await self.files.insert_one({'file_id': file_id, 'unique_id': unique_id, 'caption': caption})
        except Exception as e:
            logger.error(f"Add file error: {e}")

    async def get_file(self, unique_id):
        return await self.files.find_one({'unique_id': unique_id})

    async def total_files_count(self):
        return await self.files.count_documents({})

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_readable_time(seconds: int) -> str:
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = []
    for name, sec in periods:
        if seconds >= sec:
            value, seconds = divmod(seconds, sec)
            result.append(f"{int(value)}{name}")
    return ' '.join(result) or '0s'

def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += "=" * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

async def is_user_joined(client: Client, user_id: int, channel) -> bool:
    if channel in ("0", 0):
        return True
    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status != enums.ChatMemberStatus.BANNED
    except UserNotParticipant:
        return False
    except:
        return True

def get_file_type(message: Message) -> str:
    if message.document: return "document"
    if message.video: return "video"
    if message.audio: return "audio"
    if message.photo: return "photo"
    if message.voice: return "voice"
    if message.video_note: return "video_note"
    if message.sticker: return "sticker"
    if message.animation: return "animation"
    return "unknown"

async def get_file_id_and_ref(message: Message) -> Tuple[str,str]:
    f_type = get_file_type(message)
    if f_type == "document": return message.document.file_id, message.document.file_unique_id
    if f_type == "video": return message.video.file_id, message.video.file_unique_id
    if f_type == "audio": return message.audio.file_id, message.audio.file_unique_id
    if f_type == "photo": return message.photo.file_id, message.photo.file_unique_id
    if f_type == "voice": return message.voice.file_id, message.voice.file_unique_id
    if f_type == "video_note": return message.video_note.file_id, message.video_note.file_unique_id
    if f_type == "sticker": return message.sticker.file_id, message.sticker.file_unique_id
    if f_type == "animation": return message.animation.file_id, message.animation.file_unique_id
    return None, None

# ============================================
# BOT INITIALIZATION
# ============================================

Bot = Client(
    "FileShareBot",
    api_id=Config.APP_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=50
)

db = Database(Config.DB_URL, Config.DB_NAME)
BOT_START_TIME = time.time()

# ============================================
# COMMAND HANDLERS
# ============================================

@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    start_text = Config.START_MESSAGE.format(mention=message.from_user.mention)
    buttons = [[
        InlineKeyboardButton("📢 Updates", url="https://t.me/JishuBotz"),
        InlineKeyboardButton("🛠 Support", url="https://t.me/JishuDeveloper")
    ]]
    await message.reply_text(start_text, reply_markup=InlineKeyboardMarkup(buttons), quote=True)

@Bot.on_message(filters.command("genlink") & filters.user(Config.ADMINS) & filters.private)
async def genlink_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("📝 Usage:\n/genlink [message_id]\nExample: /genlink 100")
        return
    try:
        msg_id = int(message.command[1])
        msg = await client.get_messages(Config.CHANNEL_ID, msg_id)
        if not msg:
            await message.reply_text("❌ Message not found!")
            return
        encoded = encode_file_id(str(msg_id))
        bot_username = (await client.get_me()).username
        link = f"https://t.me/{bot_username}?start={encoded}"
        await message.reply_text(f"✅ Link Generated!\n🔗 Link: `{link}`", quote=True)
    except Exception as e:
        logger.error(f"genlink error: {e}")
        await message.reply_text(f"❌ Error: {e}")

# ============================================
# MAIN EXECUTION
# ============================================

async def main():
    await start_health_server()
    await Bot.start()
    logger.info("Bot started successfully!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    logger.info("Starting Bot...")
    if not Config.BOT_TOKEN or not Config.API_HASH or Config.APP_ID==0 or Config.CHANNEL_ID==0 or not Config.DB_URL:
        logger.error("Missing required config!")
        sys.exit(1)
    asyncio.run(main())
