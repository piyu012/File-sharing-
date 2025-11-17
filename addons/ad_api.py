import os, hmac, hashlib, time, asyncio, requests, base64, urllib.parse
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
ADRINO_API = os.getenv("ADRINO_API")   # Adrinolinks API KEY
MONGO_URI = os.getenv("MONGO_URI")     # MongoDB URI
DB_NAME = "filesharebott"              # Explicit database name

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
        api_url = f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        r = requests.get(api_url).json()
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

# ---------------- Base64 URL decode with padding ----------------
def decode_base64_urlsafe(data: str):
    data = urllib.parse.unquote(data)  # URL decode first
    data += '=' * (-len(data) % 4)      # Fix padding
    return base64.urlsafe_b64decode(data.encode()).decode()

# ---------------- BOT HANDLER ----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    ts = int(time.time())

    payload = f"{uid}:{ts}"
    sig = sign(payload)

    # ===== Combine payload & sig in Base64 =====
    payload_sig = f"{payload}:{sig}"
    encoded_all = base64.urlsafe_b64encode(payload_sig.encode()).decode()
    encoded_all = urllib.parse.quote(encoded_all)  # URL safe

    long_link = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/watch?data={encoded_all}"
    short_url = short_adrinolinks(long_link)

    # ---------------- STORE IN DB ----------------
    await tokens_col.insert_one({
        "uid": uid,
        "payload": payload,
        "sig": sig,
        "created_at": datetime.utcnow(),
        "used": False
    })

    await message.reply_text(
        f"👋 Welcome!\n\n👉 Your short ad link:\n\n{short_url}"
    )

# ---------------- WATCH PAGE ----------------
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    try:
        decoded = decode_base64_urlsafe(data)
        payload, sig = decoded.split(":")
    except:
        raise HTTPException(400, "Invalid data")

    token_doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not token_doc:
        raise HTTPException(404, "Token not found")

    # Check 24 hours validity
    if datetime.utcnow() - token_doc["created_at"] > timedelta(hours=24):
        raise HTTPException(403, "Token expired")
    
    if token_doc["used"]:
        raise HTTPException(403, "Token already used")

    return f"""
    <html>
    <body>
      <h2>Watch Ad</h2>
      <p>Wait 6 seconds…</p>
      <script>
      setTimeout(function(){{
          window.location.href="/callback?data={urllib.parse.quote(data)}";
      }},6000);
      </script>
    </body>
    </html>
    """

# ---------------- CALLBACK ----------------
@api.get("/callback")
async def callback(data: str):
    try:
        decoded = decode_base64_urlsafe(data)
        payload, sig = decoded.split(":")
    except:
        raise HTTPException(400, "Invalid data")

    token_doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not token_doc:
        raise HTTPException(404, "Token not found")

    # Check 24 hours validity
    if datetime.utcnow() - token_doc["created_at"] > timedelta(hours=24):
        raise HTTPException(403, "Token expired")
    
    if token_doc["used"]:
        raise HTTPException(403, "Token already used")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    # Mark token as used
    await tokens_col.update_one(
        {"_id": token_doc["_id"]},
        {"$set": {"used": True}}
    )

    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
