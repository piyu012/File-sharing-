import os, hmac, hashlib, time, asyncio, requests, base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ---------------- ENV ----------------
def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v or v.strip() == "":
        raise RuntimeError(f"Missing env: {name}")
    return v

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = require_env("BOT_TOKEN")
API_ID = int(require_env("API_ID"))
API_HASH = require_env("API_HASH")
ADRINO_API = os.getenv("ADRINO_API", "")
MONGO_URI = require_env("MONGO_URI")
DB_NAME = "filesharebott"
ADMIN_ID = int(require_env("ADMIN_ID"))
BOT_USERNAME = require_env("BOT_USERNAME")
DB_CHANNEL = int(require_env("DB_CHANNEL"))

# ---------------- Pyrogram Client ----------------
bot = Client("adbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
bot.db_channel = DB_CHANNEL
ADMINS = [ADMIN_ID]

# ---------------- MongoDB ----------------
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens

# ---------------- Helper Functions ----------------
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(long_url):
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}", timeout=10).json()
        return r.get("shortenedUrl", long_url)
    except Exception:
        return long_url

# ---------------- FastAPI Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[STARTUP] Starting Pyrogram bot...", flush=True)
    await bot.start()
    print("[STARTUP] Bot started successfully!", flush=True)
    try:
        yield
    finally:
        print("[SHUTDOWN] Stopping bot...", flush=True)
        await bot.stop()
        mongo.close()
        print("[SHUTDOWN] Bot stopped.", flush=True)

api = FastAPI(lifespan=lifespan)

# ---------------- Root endpoint ----------------
@api.get("/")
async def root():
    return {"status": "Bot is running", "message": "File sharing bot active"}

# ============================================================
#                     START COMMAND
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    print(f"[LOG] /start from user {uid}", flush=True)
    now = datetime.utcnow()

    existing = await tokens_col.find_one({"uid": uid, "used": True, "expires_at": {"$gt": now}})
    if existing:
        exp = existing["expires_at"].strftime("%Y-%m-%d %H:%M:%S")
        await message.reply_text(f"Token already active! Valid till: {exp}")
        return

    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)
    expire_time = now + timedelta(hours=12)

    await tokens_col.insert_one({
        "uid": uid, "payload": payload, "sig": sig,
        "created_at": now, "used": False, "activated_at": None, "expires_at": expire_time
    })

    print(f"[LOG] New token created for {uid}", flush=True)

    try:
        await bot.send_message(ADMIN_ID, f"Token generated for user {uid}")
    except Exception as e:
        print(f"[LOG] Admin notify failed: {e}", flush=True)

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
    base_url = f"https://{host}" if host else ""
    url = f"{base_url}/watch?data={encoded}"
    short_url = short_adrinolinks(url)

    await message.reply_text(f"Activate your token: {short_url}")

# ============================================================
#                     WATCH & CALLBACK
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    print(f"[LOG] /watch called", flush=True)
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except Exception:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()
    if doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")
    if doc["used"]:
        raise HTTPException(403, "Already used")

    return f'<html><head><meta http-equiv="refresh" content="0; url=/callback?data={data}"/></head><body>Redirecting...</body></html>'

@api.get("/callback")
async def callback(data: str):
    print(f"[LOG] /callback called", flush=True)
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except Exception:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()
    if doc["expires_at"] < now or doc["used"]:
        raise HTTPException(403, "Expired or used")

    uid, ts = payload.split(":")
    new_expiry = now + timedelta(hours=12)
    await tokens_col.update_one({"_id": doc["_id"]}, {"$set": {"used": True, "activated_at": now, "expires_at": new_expiry}})

    print(f"[LOG] Token activated for {uid}", flush=True)

    try:
        await bot.send_message(ADMIN_ID, f"Token activated by user {uid}")
    except Exception:
        pass

    await bot.send_message(int(uid), "Token verified! Valid for 12 hours.")

    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=done"
    return HTMLResponse(f'<html><head><meta http-equiv="refresh" content="0; url={deep_link}"/></head><body>Redirecting...</body></html>')

# ============================================================
#             FILE LINK GENERATOR
# ============================================================
@bot.on_message(filters.private & (filters.document | filters.photo | filters.video | filters.audio))
async def file_link_generator(client: Client, message: Message):
    uid = message.from_user.id
    print(f"[LOG] Media received from user {uid}", flush=True)
    
    if uid not in ADMINS:
        await message.reply_text("Only admin can generate links.")
        print(f"[LOG] User {uid} is not admin", flush=True)
        return
    
    reply_text = await message.reply_text("Generating link...", quote=True)

    if not bot.db_channel:
        await reply_text.edit_text("DB Channel not configured!")
        print("[ERROR] DB_CHANNEL not set", flush=True)
        return

    try:
        post_message = await message.copy(chat_id=bot.db_channel, disable_notification=True)
        print(f"[LOG] File copied to channel. Message ID: {post_message.id}", flush=True)
    except Exception as e:
        await reply_text.edit_text(f"Copy failed: {e}")
        print(f"[ERROR] Copy failed: {e}", flush=True)
        return

    converted_id = post_message.id * abs(bot.db_channel)
    string = f"get-{converted_id}"
    base64_string = base64.urlsafe_b64encode(string.encode()).decode()
    link = f"https://t.me/{BOT_USERNAME}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Share Link", url=f"https://telegram.me/share/url?url={link}")]])

    await reply_text.edit(f"Link generated: {link}", reply_markup=reply_markup, disable_web_page_preview=True)

    try:
        await post_message.edit_reply_markup(reply_markup)
        print("[LOG] Channel post updated", flush=True)
    except Exception as e:
        print(f"[LOG] Markup edit failed: {e}", flush=True)

print("[INIT] Bot loaded. Ready for startup.", flush=True)
