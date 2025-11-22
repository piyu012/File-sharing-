import os
import asyncio
import base64
import logging
from datetime import datetime
from aiohttp import web
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bot")

# ---------------- Env Vars ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
PORT = int(os.getenv("PORT", 8080))

# ---------------- Bot & DB ----------------
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app = FastAPI()

db = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL).telegram_bot
videos = db.videos

# -------- Save photo ----------
async def save_photo(title, file_id):
    exists = await videos.find_one({"file_id": file_id})
    if exists:
        return False

    await videos.insert_one({
        "title": title,
        "file_id": file_id,
        "is_photo": True,
        "uploaded_at": datetime.utcnow()
    })
    return True

# -------- Save video ----------
async def save_video(title, file_id):
    exists = await videos.find_one({"file_id": file_id})
    if exists:
        return False

    await videos.insert_one({
        "title": title,
        "file_id": file_id,
        "is_photo": False,
        "uploaded_at": datetime.utcnow()
    })
    return True

# -------- Link generator ----------
def generate_short_link(file_id):
    bot_user = bot.me.username
    encoded = base64.urlsafe_b64encode(f"get-{file_id}".encode()).decode().rstrip("=")
    return f"https://t.me/{bot_user}?start={encoded}"

# -------- Decode ----------
def decode_payload(encoded):
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        if decoded.startswith("get-"):
            return decoded.replace("get-", "")
        return None
    except:
        return None

# -------- /start handler ----------
@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        payload = decode_payload(message.command[1])
        if not payload:
            return await message.reply("❌ Invalid link.")

        file = await videos.find_one({"file_id": payload})
        if not file:
            return await message.reply("❌ File not found in database.")

        if file["is_photo"]:
            return await message.reply_photo(
                file["file_id"],
                caption=f"📸 *Your photo*\nTitle: {file['title']}"
            )
        else:
            return await message.reply_video(
                file["file_id"],
                caption=f"🎥 *Your video*\nTitle: {file['title']}"
            )

    return await message.reply("👋 Send me photo or video and I will give you a short link.")

# -------- Photo handler ----------
@bot.on_message(filters.photo)
async def photo_handler(client, message):
    title = message.caption or "Photo"
    file_id = message.photo.file_id

    saved = await save_photo(title, file_id)
    link = generate_short_link(file_id)

    if saved:
        await message.reply(f"📸 Photo saved!\n🔗 Link: `{link}`")
    else:
        await message.reply(f"⚠ Already exists.\n🔗 Link: `{link}`")

# -------- Video handler ----------
@bot.on_message(filters.video)
async def video_handler(client, message):
    title = message.caption or "Video"
    file_id = message.video.file_id

    saved = await save_video(title, file_id)
    link = generate_short_link(file_id)

    if saved:
        await message.reply(f"🎥 Video saved!\n🔗 Link: `{link}`")
    else:
        await message.reply(f"⚠ Already exists.\n🔗 Link: `{link}`")

# -------- Cleanup task ----------
async def cleanup_task():
    while True:
        await asyncio.sleep(60)

# -------- HTTP server ----------
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

    logger.info(f"HTTP server running on {PORT}")

# -------- Main runner ----------
async def main_runner():
    await bot.start()
    logger.info("Bot started.")

    asyncio.create_task(start_http_server())
    asyncio.create_task(cleanup_task())

    await asyncio.Event().wait()

# -------- Start bot ----------
if __name__ == "__main__":
    try:
        bot.run(main_runner())
    except Exception as e:
        logger.error(f"Startup Error: {e}", exc_info=True)
