import os
import sys
import asyncio
import datetime
import logging
import base64
import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
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

    TOKEN_VALID_HOURS = int(os.environ.get("TOKEN_VALID_HOURS", "12"))
    ADRINOLINKS_API_KEY = os.environ.get("ADRINOLINKS_API_KEY", "")
    ADRINOLINKS_SECRET = os.environ.get("ADRINOLINKS_SECRET", "")
    ADRINOLINKS_BASE = "https://adrinolinks.in/api"

# ---------------- DATABASE ----------------
class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db['users']
        self.files = self.db['file_ids']

    async def add_user(self, user_id, first_name, username):
        await self.users.update_one(
            {'id': user_id},
            {'$set': {'id': user_id, 'first_name': first_name, 'username': username, 'join_date': datetime.datetime.utcnow()}},
            upsert=True
        )

    async def add_file(self, file_id, unique_id, caption=None):
        await self.files.insert_one({'file_id': file_id, 'unique_id': unique_id, 'caption': caption})

    async def set_token(self, user_id, hours=Config.TOKEN_VALID_HOURS):
        expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        await self.users.update_one({'id': user_id}, {'$set': {'token_expiry': expiry}}, upsert=True)
        return expiry

    async def is_token_valid(self, user_id):
        user = await self.users.find_one({'id': user_id})
        return user and 'token_expiry' in user and datetime.datetime.utcnow() < user['token_expiry']

# ---------------- UTILS ----------------
def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += "=" * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

async def generate_ad_link(user_id: int) -> str:
    """Generate adrinolinks short link with secret verification"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            params = {
                "apikey": Config.ADRINOLINKS_API_KEY,
                "url": f"https://file-sharing-yw4r.onrender.com/ad_complete?user={user_id}&secret={Config.ADRINOLINKS_SECRET}"
            }
            resp = await client.get(Config.ADRINOLINKS_BASE, params=params)
            data = resp.json()
            return data.get("shortened", f"https://file-sharing-yw4r.onrender.com/ad_complete?user={user_id}&secret={Config.ADRINOLINKS_SECRET}")
    except Exception as e:
        logger.error(f"Ad link generation error: {e}")
        return f"https://file-sharing-yw4r.onrender.com/ad_complete?user={user_id}&secret={Config.ADRINOLINKS_SECRET}"

# ---------------- BOT SETUP ----------------
Bot = Client("FileShareBot", api_id=Config.APP_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, workers=50)
db = Database(Config.DB_URL, Config.DB_NAME)

# ---------------- HEALTH SERVER ----------------
async def health_check(request):
    return web.Response(text="Bot is running! ✅", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    # ad_complete webhook with secret verification
    async def ad_complete(request):
        try:
            user_id = int(request.query.get("user"))
            secret = request.query.get("secret")
            if secret != Config.ADRINOLINKS_SECRET:
                return web.Response(text="❌ Invalid request!", status=403)
            await db.set_token(user_id)
            return web.Response(text="✅ Token activated! Return to Telegram.", status=200)
        except Exception as e:
            return web.Response(text=f"❌ Error: {e}", status=500)

    app.router.add_get('/ad_complete', ad_complete)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Health server running on port {Config.PORT}")

# ---------------- SEND FILE ----------------
async def send_file(client, user, encoded_file_id: str):
    try:
        decoded_id = int(decode_file_id(encoded_file_id))
        msg = await client.get_messages(Config.CHANNEL_ID, decoded_id)
        if not msg:
            await client.send_message(user.id, "❌ File not found.")
            return
        await msg.copy(chat_id=user.id, caption=msg.caption, protect_content=Config.PROTECT_CONTENT)
    except Exception as e:
        await client.send_message(user.id, f"❌ Error: {e}")

# ---------------- OWNER AUTO LINK ----------------
@Bot.on_message(filters.private & filters.user(Config.OWNER_ID))
async def owner_auto_link(client, message: Message):
    ftype = "document" if message.document else "unknown"
    if ftype == "unknown": return
    sent_msg = await message.copy(chat_id=Config.CHANNEL_ID)
    file_id, unique_id = sent_msg.document.file_id, sent_msg.document.file_unique_id
    await db.add_file(file_id, unique_id, sent_msg.caption)
    encoded = encode_file_id(str(sent_msg.id))
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={encoded}"
    await message.reply_text(f"✅ File uploaded!\n🔗 {share_link}", quote=True)

# ---------------- START COMMAND ----------------
@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

    if message.from_user.id == Config.OWNER_ID:
        await message.reply_text("Hi owner! Upload enabled.", quote=True)
        return

    valid = await db.is_token_valid(message.from_user.id)
    if not valid:
        ad_url = await generate_ad_link(message.from_user.id)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Renew Token", url=ad_url)]])
        await message.reply_text("❌ Token expired! Watch ad to renew.", reply_markup=keyboard, quote=True)
        return

    if len(message.command) > 1:
        await send_file(client, message.from_user, message.command[1])
    else:
        text = Config.START_MESSAGE.format(mention=message.from_user.mention)
        await message.reply_text(f"✅ Token valid for {Config.TOKEN_VALID_HOURS} hours.\n{text}", quote=True)

# ---------------- MAIN ----------------
async def main():
    await start_health_server()
    await Bot.start()
    logger.info("Bot started! Owner upload + token system with adrinolinks verification enabled.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not all([Config.BOT_TOKEN, Config.API_HASH, Config.APP_ID, Config.CHANNEL_ID, Config.DB_URL, Config.ADRINOLINKS_API_KEY, Config.ADRINOLINKS_SECRET]):
        logger.error("Please set all environment variables including ADRINOLINKS_SECRET!")
        sys.exit(1)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped!")
