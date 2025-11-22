import os
import sys
import time
import asyncio
import datetime
import logging
import traceback
from typing import Union

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant

from motor.motor_asyncio import AsyncIOMotorClient
import base64
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    START_MESSAGE = os.environ.get("START_MESSAGE", "<b>Hi {mention}! Welcome to the File Sharing Bot.</b>")
    FORCE_SUB_MESSAGE = os.environ.get("FORCE_SUB_MESSAGE", "<b>📌 Please join @{channel} first to use this bot.</b>")
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "")
    DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False").lower() == "true"
    BOT_STATS_TEXT = os.environ.get("BOT_STATS_TEXT", "<b>📊 Uptime: {uptime}\nUsers: {users}\nFiles: {files}</b>")
    USER_REPLY_TEXT = os.environ.get("USER_REPLY_TEXT", "<b>❌ Invalid command! Use /start to begin.</b>")

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
    logger.info(f"Health server running on port {Config.PORT}")

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db['users']
        self.files = self.db['file_ids']

    async def add_user(self, user_id, first_name, username):
        try:
            user_data = {'id': user_id, 'first_name': first_name, 'username': username, 'join_date': datetime.datetime.now()}
            await self.users.update_one({'id': user_id}, {'$set': user_data}, upsert=True)
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    async def get_all_users(self):
        return await self.users.find().to_list(length=None)

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def add_file(self, file_id, unique_id, caption=None):
        try:
            await self.files.insert_one({'file_id': file_id, 'unique_id': unique_id, 'caption': caption})
        except Exception as e:
            logger.error(f"Error adding file: {e}")

    async def total_files_count(self):
        return await self.files.count_documents({})

def get_readable_time(seconds: int) -> str:
    periods = [('d', 60*60*24), ('h', 60*60), ('m', 60), ('s', 1)]
    result = []
    for name, sec in periods:
        if seconds >= sec:
            val, seconds = divmod(seconds, sec)
            result.append(f'{int(val)}{name}')
    return ' '.join(result) if result else '0s'

def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += "=" * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

async def is_user_joined(client: Client, user_id: int, channel) -> bool:
    if channel == "0" or channel == 0:
        return True
    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status != enums.ChatMemberStatus.BANNED
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
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

async def get_file_id_and_ref(message: Message) -> tuple:
    ftype = get_file_type(message)
    if ftype == "document": return message.document.file_id, message.document.file_unique_id
    if ftype == "video": return message.video.file_id, message.video.file_unique_id
    if ftype == "audio": return message.audio.file_id, message.audio.file_unique_id
    if ftype == "photo": return message.photo.file_id, message.photo.file_unique_id
    if ftype == "voice": return message.voice.file_id, message.voice.file_unique_id
    if ftype == "video_note": return message.video_note.file_id, message.video_note.file_unique_id
    if ftype == "sticker": return message.sticker.file_id, message.sticker.file_unique_id
    if ftype == "animation": return message.animation.file_id, message.animation.file_unique_id
    return None, None

Bot = Client("FileShareBot", api_id=Config.APP_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, workers=50, sleep_threshold=10)
db = Database(Config.DB_URL, Config.DB_NAME)
BOT_START_TIME = time.time()

# ------------------- Handlers -------------------

@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

    if len(message.command) > 1:
        encoded_file_id = message.command[1]
        if Config.FORCE_SUB_CHANNEL != "0":
            joined = await is_user_joined(client, message.from_user.id, Config.FORCE_SUB_CHANNEL)
            if not joined:
                invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
                text = Config.FORCE_SUB_MESSAGE.format(channel=str(Config.FORCE_SUB_CHANNEL).replace("-100",""))
                buttons = [[InlineKeyboardButton("📌 Join Channel", url=invite_link.invite_link)],
                           [InlineKeyboardButton("🔄 Try Again", callback_data=f"check_sub:{encoded_file_id}")]]
                await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), quote=True)
                return
        await send_file(client, message, encoded_file_id)
    else:
        text = Config.START_MESSAGE.format(mention=message.from_user.mention)
        await message.reply_text(text, quote=True)

async def send_file(client: Client, message: Message, encoded_file_id: str):
    try:
        decoded_ids = decode_file_id(encoded_file_id).split("-")
        for fid in decoded_ids:
            msg = await client.get_messages(Config.CHANNEL_ID, int(fid))
            if msg:
                caption = msg.caption
                if Config.CUSTOM_CAPTION and msg.document:
                    caption = Config.CUSTOM_CAPTION.format(filename=msg.document.file_name, previouscaption=msg.caption or "")
                await msg.copy(chat_id=message.from_user.id, caption=caption, protect_content=Config.PROTECT_CONTENT, reply_markup=None)
        if Config.FILE_AUTO_DELETE > 0:
            await asyncio.sleep(Config.FILE_AUTO_DELETE)
            try: await message.delete()
            except: pass
    except Exception as e:
        logger.error(f"Error in send_file: {e}")

@Bot.on_message(filters.channel & filters.chat(Config.CHANNEL_ID))
async def save_file(client: Client, message: Message):
    try:
        if get_file_type(message) == "unknown": return
        file_id, unique_id = await get_file_id_and_ref(message)
        if not file_id: return
        await db.add_file(file_id, unique_id, message.caption)
        encoded = encode_file_id(str(message.id))
        share_link = f"https://t.me/{(await client.get_me()).username}?start={encoded}"
        text = f"✅ Link Generated!\n📄 File ID: {message.id}\n🔗 {share_link}"
        await client.send_message(Config.OWNER_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error saving file: {e}")

@Bot.on_callback_query(filters.regex(r"^check_sub:"))
async def check_sub_callback(client: Client, query: CallbackQuery):
    encoded_file_id = query.data.split(":",1)[1]
    joined = await is_user_joined(client, query.from_user.id, Config.FORCE_SUB_CHANNEL)
    if joined:
        await query.answer("✅ Verified!", show_alert=True)
        await query.message.delete()
        class Dummy:
            def __init__(self, user, client):
                self.from_user = user
                self.chat = user
                self.client = client
            async def reply_text(self, text, **kwargs): return await client.send_message(self.from_user.id, text)
        await send_file(client, Dummy(query.from_user, client), encoded_file_id)
    else:
        await query.answer("❌ Not joined yet!", show_alert=True)

async def main():
    await start_health_server()
    await Bot.start()
    logger.info("Bot started! Automatic link generation enabled!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not Config.BOT_TOKEN or not Config.API_HASH or Config.APP_ID==0 or Config.CHANNEL_ID==0 or not Config.DB_URL:
        logger.error("Please set all required environment variables!")
        sys.exit(1)
    loop = asyncio.get_event_loop()
    try: loop.run_until_complete(main())
    except KeyboardInterrupt: logger.info("Bot stopped!")
