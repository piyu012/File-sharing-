import os, hmac, hashlib, time, asyncio, requests, base64, contextlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ---------------- ENV (safe) ----------------
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
DB_CHANNEL = int(require_env("DB_CHANNEL"))  # e.g. -100xxxxxxxxxx

# ---------------- FastAPI with lifespan ----------------
pyro_heartbeat_task = None

bot = Client(
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
bot.db_channel = DB_CHANNEL
ADMINS = [ADMIN_ID]

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]
tokens_col = db.tokens

def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(long_url):
    try:
        r = requests.get(
            f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}",
            timeout=10
        ).json()
        return r.get("shortenedUrl", long_url)
    except Exception:
        return long_url

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pyro_heartbeat_task
    await bot.start()
    async def _ping():
        while True:
            await asyncio.sleep(3600)
    pyro_heartbeat_task = asyncio.create_task(_ping())
    try:
        yield
    finally:
        if pyro_heartbeat_task:
            pyro_heartbeat_task.cancel()
            with contextlib.suppress(Exception):
                await pyro_heartbeat_task
        await bot.stop()
        mongo.close()

api = FastAPI(lifespan=lifespan)

# ============================================================
#                     START COMMAND
# ============================================================
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    print(f"[LOG] /start command received from {message.from_user.id}", flush=True)
    uid = message.from_user.id
    now = datetime.utcnow()

    existing = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if existing:
        exp = existing["expires_at"].strftime("%Y-%m-%d %H:%M:%S")
        print(f"[LOG] User {uid} already has active token", flush=True)
        await message.reply_text(
            (
                f"✅ आपका token पहले से activate है!
"
                f"⏳ Valid till: {exp}

"
                f"आपको ad दुबारा देखने की जरूरत नहीं है।"
            )
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

    print(f"[LOG] New token created for {uid}", flush=True)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 New token generated for user {uid}
Payload: {payload}"
        )
    except Exception as e:
        print(f"[LOG] Admin notification failed: {e}", flush=True)

    encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
    base_host = f"https://{host}" if host else ""
    url = f"{base_host}/watch?data={encoded}" if base_host else f"/watch?data={encoded}"
    short_url = short_adrinolinks(url)

    await message.reply_text(
        f"🔗 आपका token activate करने के लिए नीचे ad देखें:

{short_url}"
    )

# ============================================================
#                     WATCH PAGE
# ============================================================
@api.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    print(f"[LOG] /watch called with data={data}", flush=True)
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
    print(f"[LOG] /callback called with data={data}", flush=True)
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
        raise HTTPException(403, "Token expired or already used")

    uid, ts = payload.split(":")
    new_expiry = now + timedelta(hours=12)
    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "activated_at": now, "expires_at": new_expiry}}
    )

    print(f"[LOG] Token activated for user {uid}", flush=True)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 Token activated by {uid}
Valid till: {new_expiry}"
        )
    except Exception:
        pass

    await bot.send_message(
        int(uid),
        "✅ आपका token verify हो गया!
⏳ Valid for: 12 Hour"
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
#             ADMIN ONLY FILE/PHOTO/VIDEO LINK GENERATOR
# ============================================================
@bot.on_message(
    filters.private &
    (filters.document | filters.photo | filters.video | filters.audio) &
    filters.user(ADMINS)
)
async def file_link_generator(client: Client, message: Message):
    print(f"[LOG] File handler triggered by {message.from_user.id}", flush=True)

    reply_text = await message.reply_text("⏳ Please wait, generating link...", quote=True)

    if not getattr(bot, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        print("[LOG] DB channel not set", flush=True)
        return

    try:
        post_message = await message.copy(
            chat_id=bot.db_channel,
            disable_notification=True
        )
        print(f"[LOG] Media copied to DB channel: {bot.db_channel}, message_id: {post_message.id}", flush=True)
    except Exception as e:
        await reply_text.edit_text(f"❌ Something went wrong: {e}")
        print(f"[LOG] Copy failed: {e}", flush=True)
        return

    converted_id = post_message.id * abs(bot.db_channel)
    string = f"get-{converted_id}"
    base64_string = base64.urlsafe_b64encode(string.encode()).decode()
    link = f"https://t.me/{BOT_USERNAME}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]]
    )

    await reply_text.edit(
        f"<b>Here is your link</b>:

{link}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    try:
        await post_message.edit_reply_markup(reply_markup)
        print("[LOG] DB channel post markup updated", flush=True)
    except Exception as e:
        print("[LOG] Edit Reply Markup Failed:", e, flush=True)
