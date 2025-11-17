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
ADRINO_API = os.getenv("ADRINO_API")   # Adrinolinks API KEY
MONGO_URI = os.getenv("MONGO_URI")     # MongoDB URI
DB_NAME = "filesharebott"

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

# ---------------- BOT HANDLER ----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    now = datetime.utcnow()
    expire_time = now + timedelta(hours=12)

    # --------- Check existing active token ---------
    token_doc = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if token_doc:
        # Token exists & active → reuse
        payload = token_doc["payload"]
        sig = token_doc["sig"]
    else:
        # Create new token
        ts = int(time.time())
        payload = f"{uid}:{ts}"
        sig = sign(payload)

        await tokens_col.insert_one({
            "uid": uid,
            "payload": payload,
            "sig": sig,
            "created_at": now,
            "used": True,
            "expires_at": expire_time
        })

    # Encode Base64
    payload_sig = f"{payload}:{sig}"
    encoded_all = base64.urlsafe_b64encode(payload_sig.encode()).decode()
    long_link = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/watch?data={encoded_all}"
    short_url = short_adrinolinks(long_link)

    await message.reply_text(
        f"👋 Welcome!\n\n👉 Your short ad link (valid 12 hours):\n\n{short_url}"
    )

# ---------------- WATCH PAGE ----------------
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    token_doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not token_doc:
        raise HTTPException(404, "Token not found")
    
    now = datetime.utcnow()
    if token_doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")

    return f"""
    <html>
    <body>
      <h2>Watch Ad</h2>
      <p>Wait 6 seconds…</p>
      <script>
      setTimeout(function(){{
          window.location.href="/callback?data={data}";
      }},6000);
      </script>
    </body>
    </html>
    """

# ---------------- CALLBACK ----------------
@api.get("/callback")
async def callback(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    token_doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not token_doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()
    if token_doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    # Update expires_at if needed
    await tokens_col.update_one(
        {"_id": token_doc["_id"]},
        {"$set": {"used": True, "expires_at": now + timedelta(hours=12)}}
    )

    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")
    return {"ok": True, "token": token}
