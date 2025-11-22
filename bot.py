import os
import sys
import time
import asyncio
import datetime
import logging
from typing import Union

from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient
import base64
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
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
    
    START_MESSAGE = os.environ.get("START_MESSAGE", "<b>Hi {mention}! Welcome to the File Sharing Bot.</b>")
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "")

# ---------------- DATABASE ----------------
class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db['users']
        self.files = self.db['file_ids']

    async def add_user(self, user_id, first_name, username):
        try:
            user_data = {
                'id': user_id,
                'first_name': first_name,
                'username': username,
                'join_date': datetime.datetime.now()
            }
            await self.users.update_one({'id': user_id}, {'$set': user_data}, upsert=True)
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    async def add_file(self, file_id, unique_id, caption=None):
        try:
            await self.files.insert_one({'file_id': file_id, 'unique_id': unique_id, 'caption': caption})
        except Exception as e:
            logger.error(f"Error adding file: {e}")

# ---------------- UTILS ----------------
def get_file_type(message: Message) -> str:
    if message.document: return "document"
    if message.video: return "video"
    if message.audio: return "audio"
    if message.photo: return "photo"
    if message.voice: return "voice"
    if message.video_note: return "video_note"
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
    if ftype == "animation": return message.animation.file_id, message.animation.file_unique_id
    return None, None

def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += "=" * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

# ---------------- BOT SETUP ----------------
Bot = Client("FileShareBot", api_id=Config.APP_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, workers=50, sleep_threshold=10)
db = Database(Config.DB_URL, Config.DB_NAME)

# ---------------- HEALTH SERVER ----------------
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

# ---------------- SEND FILE ----------------
async def send_file(client: Client, user, encoded_file_id: str):
    try:
        decoded_id = int(decode_file_id(encoded_file_id))
        msg = await client.get_messages(Config.CHANNEL_ID, decoded_id)
        if not msg:
            await client.send_message(user.id, "❌ File not found in channel.")
            return

        ftype = get_file_type(msg)
        if ftype in ["document", "video", "audio", "photo", "voice", "animation"]:
            caption = msg.caption or ""
            if Config.CUSTOM_CAPTION and msg.document:
                caption = Config.CUSTOM_CAPTION.format(filename=msg.document.file_name, previouscaption=msg.caption or "")
            await msg.copy(chat_id=user.id, caption=caption, protect_content=Config.PROTECT_CONTENT)
        else:
            await client.send_message(user.id, "❌ Unsupported file type.")
    except Exception as e:
        await client.send_message(user.id, f"❌ Error sending file: {e}")

# ---------------- OWNER AUTO LINK ----------------
@Bot.on_message(filters.private & filters.user(Config.OWNER_ID))
async def owner_auto_link(client: Client, message: Message):
    ftype = get_file_type(message)
    if ftype == "unknown": return

    try:
        # Forward file to channel
        sent_msg = await message.copy(chat_id=Config.CHANNEL_ID)
        file_id, unique_id = await get_file_id_and_ref(sent_msg)
        await db.add_file(file_id, unique_id, sent_msg.caption)

        # Generate link
        encoded = encode_file_id(str(sent_msg.id))
        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded}"

        # Reply to owner
        await message.reply_text(
            f"✅ File uploaded successfully!\n📄 Message ID: `{sent_msg.id}`\n🔗 Share Link:\n`{share_link}`",
            quote=True
        )
    except Exception as e:
        logger.error(f"Error in owner_auto_link: {e}")
        await message.reply_text(f"❌ Error: {e}", quote=True)

# ---------------- START COMMAND ----------------
@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

    if len(message.command) > 1:
        encoded_file_id = message.command[1]
        class DummyUser:
            def __init__(self, user):
                self.id = user.id
        await send_file(client, DummyUser(message.from_user), encoded_file_id)
    else:
        text = Config.START_MESSAGE.format(mention=message.from_user.mention)
        await message.reply_text(text, quote=True)

# ---------------- MAIN ----------------
async def main():
    await start_health_server()
    await Bot.start()
    logger.info("Bot started! Owner auto link and user download enabled.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not Config.BOT_TOKEN or not Config.API_HASH or Config.APP_ID==0 or Config.CHANNEL_ID==0 or not Config.DB_URL:
        logger.error("Please set all required environment variables!")
        sys.exit(1)
    loop = asyncio.get_event_loop()
    try: loop.run_until_complete(main())
    except KeyboardInterrupt: logger.info("Bot stopped!")
