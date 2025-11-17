import os, hmac, hashlib, time, asyncio, requests, base64
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

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
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---------------- MongoDB ----------------
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens

# ---------------- HMAC SIGN ----------------
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

# ---------------- ADRINOLINKS SHORTENER ----------------
def short_adrinolinks(long_url):
    try:
        r = requests.get(
            f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        ).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

# ---------------- BOT START / STOP ----------------
@api.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# ============================================================
#                     START COMMAND FIXED
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    now = datetime.utcnow()

    # --------- Check existing activated & valid token ---------
    existing = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if existing:
        exp = existing["expires_at"].strftime("%Y-%m-%d %H:%M:%S")
        await message.reply_text(
            f"✅ आपका token पहले से activate है!\n"
            f"⏳ Valid till: {exp}\n\n"
            f"आपको ad दुबारा देखने की जरूरत नहीं है।"
        )
        return

    # --------- Create NEW token ---------
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

    # Notify admin
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 New token generated for user {uid}\nPayload: {payload}"
        )
    except:
        pass

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/watch?data={encoded}"
    short_url = short_adrinolinks(url)

    await message.reply_text(
        f"🔗 आपका token activate करने के लिए नीचे ad देखें:\n\n{short_url}"
    )

# ============================================================
#                     WATCH PAGE (NO WAIT)
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()
    if doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")

    # If user already used this token → no reuse
    if doc["used"]:
        raise HTTPException(403, "Token already used")

    return f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="0; url=/callback?data={data}" />
    </head>
    <body>Redirecting…</body>
    </html>
    """

# ============================================================
#                     CALLBACK (Activate Token)
# ============================================================
@api.get("/callback")
async def callback(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()

    if doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")

    # Prevent double-use
    if doc["used"]:
        raise HTTPException(403, "Token already used")

    uid, ts = payload.split(":")

    # -------- Activate token ---------
    new_expiry = now + timedelta(hours=12)
    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "used": True,
                "activated_at": now,
                "expires_at": new_expiry
            }
        }
    )

    # Notify admin
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 Token activated by {uid}\nValid till: {new_expiry}"
        )
    except:
        pass

    # User message
    await bot.send_message(
        int(uid),
        f"✅ आपका token verify हो गया!\n⏳ Valid for: 12 Hour"
    )

    # Auto redirect to Telegram start=done
    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=done"

    return HTMLResponse(f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="0; url={deep_link}" />
    </head>
    <body>Redirecting to Telegram…</body>
    </html>
    """)
