# main.py
import os, hmac, hashlib, time, base64, asyncio, traceback, requests
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import FastAPI
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import filters
from pyrogram.errors import MessageNotModified

from bot import bot
import config
from helper_func import encode

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
HMAC_SECRET = config.HMAC_SECRET.encode() if isinstance(config.HMAC_SECRET, str) else config.HMAC_SECRET
ADRINO_API = config.ADRINO_API
HOST = config.HOST
DB_NAME = config.DB_NAME
CHANNEL_ID = config.CHANNEL_ID
ADMIN_ID = config.ADMIN_ID
BOT_USERNAME = config.BOT_USERNAME

# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------
mongo = AsyncIOMotorClient(config.MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens


# ---------------------------------------------------------
# Lifespan (startup + shutdown)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Pyrogram Bot...")
    await bot.start()

    # load channel
    try:
        bot.db_channel = await bot.get_chat(CHANNEL_ID)
        print("✅ db_channel loaded:", bot.db_channel.id)
    except Exception as e:
        bot.db_channel = None
        print("⚠️ Failed to load db_channel:", e)

    print("Bot Ready ✔️")
    yield

    print("🛑 Stopping Bot...")
    try:
        await bot.stop()
    except:
        pass


api = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------
# UTILS
# ---------------------------------------------------------
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(url: str):
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={url}", timeout=8).json()
        return r.get("shortenedUrl") or url
    except:
        return url


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
@api.get("/", response_class=HTMLResponse)
async def root():
    return "<h3>FastAPI + Pyrogram file bot is running.</h3>"


@api.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@api.get("/gen", response_class=HTMLResponse)
async def gen(uid: int = Query(...)):
    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)
    now = datetime.utcnow()

    await tokens_col.insert_one({
        "uid": uid,
        "payload": payload,
        "sig": sig,
        "created_at": now,
        "used": False,
        "activated_at": None,
        "expires_at": now + timedelta(hours=12)
    })

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    watch_url = f"https://{HOST}/watch?data={encoded}"
    short = short_adrinolinks(watch_url)

    return f"<a href='{short}'>Your Ad Link</a>"


@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str = Query(...)):
    return f"""
    <html>
    <head><meta http-equiv='refresh' content='0; url=/callback?data={data}' /></head>
    <body>Loading...</body>
    </html>
    """


@api.get("/callback", response_class=HTMLResponse)
async def callback(data: str = Query(...)):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    uid, ts = payload.split(":")
    uid = int(uid)
    now = datetime.utcnow()

    await tokens_col.update_one({"_id": doc["_id"]}, {
        "$set": {
            "used": True,
            "activated_at": now,
            "expires_at": now + timedelta(hours=12)
        }
    })

    try:
        await bot.send_message(uid, "✅ आपका Ad Token Activate हो गया!")
    except:
        pass

    deep = f"tg://resolve?domain={BOT_USERNAME}&start=done"
    return f"<meta http-equiv='refresh' content='0; url={deep}' />"


# ---------------------------------------------------------
# MESSAGE HANDLER
# ---------------------------------------------------------
@bot.on_message(filters.private & ~filters.command(["start", "help"]))
async def handle_file(client, message):
    try:
        if not bot.db_channel:
            return await message.reply_text("⚠️ CHANNEL_ID missing or wrong")

        # Copy file/text
        posted = await message.copy(bot.db_channel.id)

        # Generate link
        converted = posted.id * abs(bot.db_channel.id)
        token = f"file-{converted}"
        b64 = base64.urlsafe_b64encode(token.encode()).decode()
        link = f"https://t.me/{BOT_USERNAME}?start={b64}"

        await message.reply_text(f"Here is your link:\n{link}")

    except Exception as e:
        traceback.print_exc()
        await message.reply_text("⚠️ Something Went Wrong..!")
