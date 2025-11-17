import os, hmac, hashlib, time, asyncio, requests, base64
from fastapi import FastAPI, HTTPException
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
        return r.get("shortenedUrl", long_url)
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
#     USER STARTS /start → CHECK TOKEN OR SHOW EXPIRED PAGE
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    now = datetime.utcnow()

    # 1️⃣ check active token
    existing = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if existing:
        return await message.reply_text(
            "🎉 आपका Ad Token पहले से एक्टिव है!\n"
            "आप बिना ad देखे बॉट इस्तेमाल कर सकते हो।"
        )

    # 2️⃣ show token expired page
    await message.reply_text(
        "❌ Your Ads token is expired.\n\n"
        "Token Timeout: 12 Hours\n\n"
        "👉 1 Ad देखो और 12 घंटे के लिए पूरा bot अनलॉक करो!",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "Click Here (Watch Ad)",
                        "url": f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/gen?uid={uid}"
                    }
                ]
            ]
        }
    )

# ============================================================
#        /gen → create new token + send short link
# ============================================================
@api.get("/gen")
async def gen(uid: int):
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
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/watch?data={encoded}"
    short = short_adrinolinks(url)

    return HTMLResponse(f"""
        <html><body>
        <h2>Your Ad Link</h2>
        <a href="{short}">{short}</a>
        </body></html>
    """)

# ============================================================
#    WATCH PAGE → redirect instantly → callback → telegram
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    return f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="0; url=/callback?data={data}" />
    </head>
    <body>Loading…</body>
    </html>
    """

# ============================================================
#    CALLBACK → final verify → telegram auto redirect
# ============================================================
@api.get("/callback")
async def callback(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    uid, ts = payload.split(":")
    uid = int(uid)

    now = datetime.utcnow()
    new_exp = now + timedelta(hours=12)

    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "activated_at": now, "expires_at": new_exp}}
    )

    await bot.send_message(uid, "✅ आपका Ad Token अब 12 घंटे के लिए एक्टिव हो गया!")

    deep = f"tg://resolve?domain={BOT_USERNAME}&start=done"

    return HTMLResponse(f"""
    <html>
    <head><meta http-equiv="refresh" content="0; url={deep}" /></head>
    <body>Redirecting…</body>
    </html>
    """)
