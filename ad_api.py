import os, hmac, hashlib, time, asyncio, requests, base64
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
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
DB_CHANNEL = int(os.getenv("DB_CHANNEL", -1001234567890))  # yaha aapka DB channel ID

api = FastAPI()

# ---------------- Pyrogram Client ----------------
bot = Client(
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

bot.db_channel = DB_CHANNEL
ADMINS = [ADMIN_ID]

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
#                     START COMMAND
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
    if doc["used"]:
        raise HTTPException(403, "Token already used")

    uid, ts = payload.split(":")
    new_expiry = now + timedelta(hours=12)
    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "activated_at": now, "expires_at": new_expiry}}
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

    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=done"
    return HTMLResponse(f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="0; url={deep_link}" />
    </head>
    <body>Redirecting to Telegram…</body>
    </html>
    """)

# ============================================================
#                     ADMIN ONLY FILE/PHOTO/VIDEO LINK GENERATOR
# ============================================================
@bot.on_message(
    filters.private
    & filters.user(ADMINS)
    & (filters.document | filters.photo | filters.video)
)
async def file_link_generator(client: Client, message: Message):
    print(f"[LOG] File handler triggered by {message.from_user.id}")

    reply_text = await message.reply_text("⏳ Please wait, generating link...", quote=True)

    if not getattr(client, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        return

    try:
        # Forward the media to DB channel
        post_message = await message.copy(
            chat_id=client.db_channel,
            disable_notification=True
        )
    except asyncio.exceptions.TimeoutError:
        await reply_text.edit_text("⚠️ Timeout occurred while forwarding!")
        return
    except Exception as e:
        await reply_text.edit_text(f"❌ Something went wrong: {e}")
        return

    # Generate unique deep link
    converted_id = post_message.id * abs(client.db_channel)
    string = f"get-{converted_id}"
    base64_string = base64.urlsafe_b64encode(string.encode()).decode()
    link = f"https://t.me/{BOT_USERNAME}?start={base64_string}"

    # Create share button
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]]
    )

    # Send link to admin
    await reply_text.edit(
        f"<b>Here is your link</b>:\n\n{link}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    # Optionally edit DB channel post with same button
    try:
        await post_message.edit_reply_markup(reply_markup)
    except Exception as e:
        print("[LOG] Edit Reply Markup Failed:", e)
        pass
