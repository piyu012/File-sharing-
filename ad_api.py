import os, hmac, hashlib, time, asyncio, requests, base64
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified

# ---------------- ENV ----------------
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADRINO_API = os.getenv("ADRINO_API")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "filesharebott"
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

api = FastAPI()

# ---------------- Pyrogram Client ----------------
bot = Client(
    "mainbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=32
)

# ---------------- MongoDB ----------------
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens


# ---------------- HMAC SIGN ----------------
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()


# ---------------- SHORTENER ----------------
def short_adrinolinks(long_url):
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}").json()
        return r.get("shortenedUrl") or long_url
    except:
        return long_url


# ---------------- BOT START (UPDATED) ----------------
@api.on_event("startup")
async def startup():
    print("🔄 Starting bot...")

    # 🔥 First start bot completely
    await bot.start()

    # 🔥 Now safely assign db_channel
    if CHANNEL_ID == 0:
        print("⚠️ CHANNEL_ID missing in ENV! channel_post.py won’t work properly.")
        bot.db_channel = None
    else:
        bot.db_channel = type("Channel", (), {"id": CHANNEL_ID})()
        print(f"✅ Bot db_channel set to {CHANNEL_ID}")

    print("🚀 Bot started successfully!")


@api.on_event("shutdown")
async def shutdown():
    await bot.stop()


# ---------------- ROOT & HEALTH ----------------
@api.get("/", response_class=HTMLResponse)
async def root():
    return f"""
    <html>
        <head><title>File Sharing Bot</title></head>
        <body>
            <h1>🎉 File Sharing Bot is Running!</h1>
            <p>Use <a href="/gen?uid=YOUR_USER_ID">/gen?uid=YOUR_USER_ID</a> to generate a token.</p>
        </body>
    </html>
    """


@api.get("/health")
async def health():
    return JSONResponse({"status": "ok", "time": datetime.utcnow().isoformat()})


# ============================================================
#     USER STARTS /start
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    username = getattr(message.from_user, "username", str(uid))
    now = datetime.utcnow()

    token = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if token:
        text = (
            f"🎉 स्वागत है @{username}!\n\n"
            "आपका Ad Token पहले से एक्टिव है, आप बिना Ad देखे बॉट इस्तेमाल कर सकते हो।"
        )
        try:
            await message.reply_text(text)
        except MessageNotModified:
            pass
    else:
        watch_url = f"https://{HOST}/gen?uid={uid}"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("Click Here (Watch Ad)", url=watch_url)]])
        text = (
            "❌ आपका Ads Token Expire हो गया है या मौजूद नहीं है!\n\n"
            "👉 सिर्फ 1 Ad देखो और पूरा bot 12 घंटे के लिए Unlock!"
        )
        try:
            await message.reply_text(text, reply_markup=btn)
        except MessageNotModified:
            pass


# ============================================================
#     /gen → generate token
# ============================================================
@api.get("/gen", response_class=HTMLResponse)
async def gen(uid: int = Query(...)):
    now = datetime.utcnow()
    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)

    expire_time = now + timedelta(hours=12)

    await tokens_col.insert_one({
        "uid": uid,
        "payload": payload,
        "sig": sig,
        "created_at": now,
        "used": False,
        "activated_at": None,
        "expires_at": expire_time
    })

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    watch_url = f"https://{HOST}/watch?data={encoded}"
    short = short_adrinolinks(watch_url)

    return f"""
    <html><body>
        <h2>Your Ad Link</h2>
        <a href="{short}">{short}</a>
    </body></html>
    """


# ============================================================
#     WATCH → redirect
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str = Query(...)):
    return f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/callback?data={data}" />
      </head>
      <body>Loading Ad...</body>
    </html>
    """


# ============================================================
#     CALLBACK → VERIFY & Activate token
# ============================================================
@api.get("/callback", response_class=HTMLResponse)
async def callback(data: str = Query(...)):
    try:
        decoded = base64.urlsafe_b64decode(data).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data format")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    uid, ts = payload.split(":")
    uid = int(uid)
    now = datetime.utcnow()

    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "used": True,
            "activated_at": now,
            "expires_at": now + timedelta(hours=12)
        }}
    )

    try:
        await bot.send_message(uid, "✅ आपका Ad Token 12 घंटे के लिए Activate हो गया!")
    except MessageNotModified:
        pass

    deep = f"tg://resolve?domain={BOT_USERNAME}&start=done"

    return f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url={deep}" />
      </head>
      <body>Redirecting...</body>
    </html>
    """
