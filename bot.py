import os
import asyncio
from aiohttp import web
import base64
import motor.motor_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bot")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
WEB_URL = os.getenv("WEB_URL")  # Example: https://your-app.onrender.com

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

app = FastAPI()
db = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL).telegram_bot
videos = db.videos  # Photo + Video दोनों इसी में स्टोर होंगे

# -----------------------
# SAVE VIDEO
# -----------------------
async def save_video(title, file_id):
    data = {
        "title": title,
        "file_id": file_id,
        "is_photo": False
    }
    try:
        await videos.insert_one(data)
        return True
    except:
        return False

# -----------------------
# SAVE PHOTO
# -----------------------
async def save_photo(title, file_id):
    data = {
        "title": title,
        "file_id": file_id,
        "is_photo": True
    }
    try:
        await videos.insert_one(data)
        return True
    except:
        return False

# -----------------------
# GENERATE SHORT LINK
# -----------------------
def generate_short_link(file_id):
    payload = f"get-{file_id}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"https://t.me/{bot.me.username}?start={encoded}"
    # -----------------------
# DECODE PAYLOAD
# -----------------------
def decode_payload(encoded: str):
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
        if decoded.startswith("get-"):
            return decoded.replace("get-", "")
        return None
    except:
        return None


# -----------------------
# START COMMAND
# -----------------------
@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        encoded = message.command[1]
        file_id = decode_payload(encoded)

        if file_id:
            # Fetch file from DB
            file_data = await videos.find_one({"file_id": file_id})

            if not file_data:
                return await message.reply("❌ File not found in database.")

            # Photo
            if file_data.get("is_photo"):
                return await message.reply_photo(
                    file_data["file_id"],
                    caption=f"📸 *Your Photo*\n\nTitle: {file_data['title']}",
                )

            # Video
            else:
                return await message.reply_video(
                    file_data["file_id"],
                    caption=f"🎥 *Your Video*\n\nTitle: {file_data['title']}",
                )

        return await message.reply("⚠ Invalid or corrupted link.")

    return await message.reply(
        "👋 Welcome! Send me any Photo/Video and I will give you a **short link**."
    )


# -----------------------
# SAVE PHOTO + GENERATE LINK
# -----------------------
@bot.on_message(filters.photo)
async def photo_handler(client, message):
    title = "Photo"  # better: you can use caption
    file_id = message.photo.file_id

    saved = await save_photo(title, file_id)

    if not saved:
        return await message.reply("⚠ Already saved. Sending link again...")

    link = generate_short_link(file_id)
    await message.reply(f"📸 *Photo Saved!*\n\n🔗 Link: `{link}`")


# -----------------------
# SAVE VIDEO + GENERATE LINK
# -----------------------
@bot.on_message(filters.video)
async def video_handler(client, message):
    title = message.caption or "Video"
    file_id = message.video.file_id

    saved = await save_video(title, file_id)

    if not saved:
        return await message.reply("⚠ Already saved. Sending link again...")

    link = generate_short_link(file_id)
    await message.reply(f"🎬 *Video Saved!*\n\n🔗 Link: `{link}`")
    # -------------------------
# PART-3: helpers, saves, link gen, web server, main
# -------------------------
import hashlib
import json
import urllib.parse

# Ensure "bot" name exists (PART-2 may have used `bot`, earlier code used `app`)
bot = globals().get("bot") or globals().get("app") or None
if bot is None:
    # fallback: if nothing defined, create one (will probably not be needed)
    bot = app  # app is expected to exist from PART-1

# ---------- DB helpers for photos + videos ----------
def _doc_exists(file_id: str) -> bool:
    return videos.find_one({"file_id": file_id}) is not None

async def save_photo(title: str, file_id: str, uploader_id: int = None):
    """
    Save photo metadata. Returns True if newly inserted, False if already existed.
    """
    try:
        if _doc_exists(file_id):
            return False
        doc = {
            "file_id": file_id,
            "is_photo": True,
            "title": title,
            "user_id": uploader_id,
            "uploaded_at": datetime.utcnow()
        }
        # use insert_one; duplicates are checked above
        videos.insert_one(doc)
        return True
    except Exception as e:
        logger.error(f"save_photo error: {e}", exc_info=True)
        return False

async def save_video_entry(title: str, file_id: str, uploader_id: int = None):
    """
    Save video metadata. Returns True if newly inserted, False if already existed.
    """
    try:
        if _doc_exists(file_id):
            return False
        doc = {
            "file_id": file_id,
            "is_photo": False,
            "title": title,
            "user_id": uploader_id,
            "uploaded_at": datetime.utcnow()
        }
        videos.insert_one(doc)
        return True
    except Exception as e:
        logger.error(f"save_video_entry error: {e}", exc_info=True)
        return False

# NOTE: PART-2 used save_video(...) name — keep wrapper to maintain compatibility
async def save_video(fid: str, uid: int, fname: str):
    return await save_video_entry(fname, fid, uid)

# ---------- link generation ----------
def generate_short_link(file_id: str, bot_username: str = None) -> str:
    """
    Create url-safe base64 payload 'get-<file_id>' and produce t.me deep-link.
    Strips padding to keep link shorter.
    """
    if not bot_username:
        # try to get username synchronously via bot if available
        try:
            bot_me = bot.get_me()
            bot_username = bot_me.username
        except Exception:
            bot_username = os.getenv("BOT_USERNAME") or ""
    raw = f"get-{file_id}".encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    if bot_username:
        return f"https://t.me/{bot_username}?start={encoded}"
    # fallback if username not available
    return f"https://t.me/your_bot?start={encoded}"

# ---------- HTTP shortening helper (optional) ----------
def shorten_url_sync_safe(long_url: str) -> str:
    """Wrapper around shorten_url_sync to avoid crashes - returns original on fail."""
    try:
        return shorten_url_sync(long_url)
    except Exception as e:
        logger.warning(f"shorten_url_sync_safe failed: {e}")
        return long_url

# ---------- Photo handler compatibility (if PART-2 expects filters.photo) ----------
# PART-2 already had @bot.on_message(filters.photo) sample — if not, add here:
@bot.on_message(filters.photo & filters.private)
async def _photo_receiver(client, message: Message):
    # Accept photo from admin only (same behavior as video) or accept from anyone? choose admin
    uid = message.from_user.id
    # Allow admin to upload, or allow all users to save (change as per requirement)
    if uid != ADMIN_ID:
        # If you want anyone to upload, comment next two lines and proceed to save
        return await message.reply_text("❌ Sirf admin photo upload kar sakta hai.")

    file_id = message.photo.file_id
    title = message.caption or "Photo"
    new = await save_photo(title, file_id, uid)
    share_link = generate_short_link(file_id, (await client.get_me()).username)
    if new:
        await message.reply_text(f"✅ Photo saved!\n🔗 Link: `{share_link}`")
    else:
        await message.reply_text(f"⚠ Photo already exists. Link: `{share_link}`")

# ---------- Main HTTP health + server start (if not already present) ----------
# If PART-1/2 already defined start_http_server, this is safe duplicate guard.
if "start_http_server" not in globals():
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

# ---------- Final main runner ----------
# If PART-1/2 already defined main & started bot, calling again will be duplicate.
if __name__ == "__main__" and not getattr(globals().get("__BOT_STARTED__"), "__bool__", lambda: False)():
    async def main_runner():
        await bot.start()
        logger.info("Bot started (main_runner).")
        # start http server and cleanup tasks if not already started
        asyncio.create_task(start_http_server())
        asyncio.create_task(cleanup_task())
        await asyncio.Event().wait()

    # mark started
    globals()["__BOT_STARTED__"] = True
    try:
        bot.run(main_runner())
    except Exception as e:
        logger.error(f"Failed to run bot: {e}", exc_info=True)

# -------------------------
# END PART-3
# -------------------------
