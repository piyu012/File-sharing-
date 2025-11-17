import os, hmac, hashlib, time, asyncio, requests, base64
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from pyrogram import Client, filters

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
        r = requests.get(
            f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        ).json()
        return r.get("shortenedUrl") or long_url
    except:
        return long_url

# ---------------- BOT START ----------------
@api.on_event("startup")
async def startup():
    asyncio.create_task(bot.start())

# ---------------- BOT STOP ----------------
@api.on_event("shutdown")
async def shutdown():
    await bot.stop()

# ============================================================
#     USER STARTS /start
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    now = datetime.utcnow()

    # Check active token
    active_token = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if active_token:
        return await message.reply_text(
            "🎉 आपका Ad Token पहले से एक्टिव है!\n"
            "आप बिना ad देखे बॉट इस्तेमाल कर सकते हो।"
        )

    # Token expired → show ad link
    watch_url = f"https://{HOST}/gen?uid={uid}"

    await message.reply_text(
        "❌ आपका Ads Token Expire हो गया है!\n\n"
        "👉 सिर्फ 1 Ad देखो और पूरा bot 12 घंटे के लिए Unlock!",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "Click Here (Watch Ad)", "url": watch_url}
                ]
            ]
        }
    )

# ============================================================
#     /gen → new token generate
# ============================================================
@api.get("/gen", response_class=HTMLResponse)
async def gen(uid: int = Query(...)):
    now = datetime.utcnow()
    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)

    expire_time = now + timedelta(hours=12)

    # Save token in DB
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
#     WATCH → redirect to callback
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str = Query(...)):
    return f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/callback?data={data}" />
      </head>
      <body>Loading Ad…</body>
    </html>
    """

# ============================================================
#     CALLBACK → VERIFY + REDIRECT TG
# ============================================================
@api.get("/callback", response_class=HTMLResponse)
async def callback(data: str = Query(...)):
    try:
        decoded = base64.urlsafe_b64decode(data).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid token format")

    # Check DB record
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

    # Notify user on Telegram
    await bot.send_message(uid, "✅ आपका Ad Token अब 12 घंटे के लिए एक्टिव हो गया!")

    deep = f"tg://resolve?domain={BOT_USERNAME}&start=done"

    return f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url={deep}" />
      </head>
      <body>Redirecting to Telegram…</body>
    </html>
    """
