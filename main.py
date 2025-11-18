# main.py
import os, hmac, hashlib, time, requests, base64, asyncio, traceback
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from motor.motor_asyncio import AsyncIOMotorClient

from pyrogram import filters
from pyrogram.errors import MessageNotModified

from bot import bot
import config
from helper_func import encode, decode

# --- env / config ---
HMAC_SECRET = config.HMAC_SECRET.encode() if isinstance(config.HMAC_SECRET, str) else config.HMAC_SECRET
ADRINO_API = config.ADRINO_API
HOST = config.HOST
DB_NAME = config.DB_NAME
CHANNEL_ID = config.CHANNEL_ID
ADMIN_ID = config.ADMIN_ID
BOT_USERNAME = config.BOT_USERNAME

api = FastAPI()

# Mongo
mongo = AsyncIOMotorClient(config.MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens

# utils
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(long_url: str) -> str:
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}", timeout=8).json()
        return r.get("shortenedUrl") or long_url
    except Exception:
        return long_url

# ---- startup/shutdown ----
@api.on_event("startup")
async def startup():
    print("🔄 FastAPI startup: starting Pyrogram bot...")
    # Start bot and then set db_channel from get_chat (guarantees bot.session ready)
    await bot.start()
    print("Pyrogram started.")

    # Try to load channel object (if provided)
    if CHANNEL_ID:
        try:
            bot.db_channel = await bot.get_chat(CHANNEL_ID)
            print("✅ db_channel loaded:", bot.db_channel.id)
        except Exception as e:
            bot.db_channel = None
            print("⚠️ Failed to load db_channel:", e)
    else:
        bot.db_channel = None
        print("⚠️ CHANNEL_ID not set in ENV.")

    print("🚀 Bot ready.")

@api.on_event("shutdown")
async def shutdown():
    try:
        await bot.stop()
    except Exception:
        pass

# ---- Routes ----
@api.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html><body>
    <h2>File Sharing Bot (FastAPI + Pyrogram) — Running</h2>
    <p>Use /gen?uid=YOUR_USER_ID to create ad link</p>
    </body></html>
    """

@api.get("/health")
async def health():
    return JSONResponse({"status": "ok", "time": datetime.utcnow().isoformat()})

# gen → show ad link (shortened)
@api.get("/gen", response_class=HTMLResponse)
async def gen(uid: int = Query(...)):
    now = datetime.utcnow()
    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)
    expire = now + timedelta(hours=12)

    await tokens_col.insert_one({
        "uid": uid,
        "payload": payload,
        "sig": sig,
        "created_at": now,
        "used": False,
        "activated_at": None,
        "expires_at": expire
    })

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    watch_url = f"https://{HOST}/watch?data={encoded}"
    short = short_adrinolinks(watch_url)

    return f"<h3>Your Ad link</h3><a href='{short}'>{short}</a>"

# watch redirects to callback (simulate ad)
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str = Query(...)):
    return f"""<html><head><meta http-equiv="refresh" content="0; url=/callback?data={data}" /></head><body>Loading...</body></html>"""

@api.get("/callback", response_class=HTMLResponse)
async def callback(data: str = Query(...)):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except Exception:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    uid, ts = payload.split(":")
    uid = int(uid)
    now = datetime.utcnow()

    await tokens_col.update_one({"_id": doc["_id"]}, {"$set": {"used": True, "activated_at": now, "expires_at": now + timedelta(hours=12)}})

    try:
        await bot.send_message(uid, "✅ आपका Ad Token 12 घंटे के लिए Activate हो गया!")
    except Exception as e:
        print("notify_user failed:", e)

    deep = f"tg://resolve?domain={BOT_USERNAME}&start=done"
    return f"""<html><head><meta http-equiv="refresh" content="0; url={deep}" /></head><body>Redirecting...</body></html>"""

# ---- File message handler: copy media/text to channel and return link ----
@bot.on_message(filters.private & ~filters.command(["start","help"]))
async def handle_user_messages(client, message):
    """Handles media/text: copies to channel and returns a t.me deep link"""
    try:
        # Ensure db_channel loaded
        if not getattr(bot, "db_channel", None):
            await message.reply_text("⚠️ Database Channel not set! Contact admin.")
            return

        # Try copy (works for most media & text)
        try:
            posted = await message.copy(chat_id=bot.db_channel.id, disable_notification=True)
        except Exception as e_copy:
            # fallback: forward
            try:
                posted = await message.forward(chat_id=bot.db_channel.id, disable_notification=True)
            except Exception as e_forw:
                # last resort: if text, send message
                if message.text:
                    posted = await bot.send_message(bot.db_channel.id, message.text, disable_notification=True)
                else:
                    raise

        # Create stable token-based link
        converted = posted.id * abs(bot.db_channel.id)
        token_str = f"file-{converted}"
        b64 = base64.urlsafe_b64encode(token_str.encode()).decode()
        link = f"https://t.me/{BOT_USERNAME}?start={b64}"

        await message.reply_text(f"✅ Saved to channel.\n🔗 {link}", disable_web_page_preview=True)
    except Exception as e:
        traceback.print_exc()
        try:
            await message.reply_text("Something Went Wrong..! (admin notified)")
        except Exception:
            pass

# ---- Small helper command for admin to gen link for a channel post id ----
@bot.on_message(filters.private & filters.user(ADMIN_ID) & filters.command(["genlink"]))
async def genlink_cmd(client, message):
    # usage: /genlink <channel_post_id>
    try:
        args = message.text.split()
        if len(args) < 2:
            return await message.reply_text("Usage: /genlink <post_id>")

        post_id = int(args[1])
        token_str = f"file-{post_id * abs(bot.db_channel.id)}"
        b64 = base64.urlsafe_b64encode(token_str.encode()).decode()
        link = f"https://t.me/{BOT_USERNAME}?start={b64}"
        await message.reply_text(link)
    except Exception as e:
        await message.reply_text("Failed: " + str(e))
