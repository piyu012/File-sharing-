import time, base64
from datetime import datetime, timedelta
from pyrogram import Client, filters
from addons.config import API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, ADMIN_ID, HOST
from utils.auth import sign
from utils.shortener import short_adrinolinks
from database.mongo import tokens_col

bot = Client(
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    now = datetime.utcnow()

    # Check active token
    existing = await tokens_col.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })

    if existing:
        exp = existing["expires_at"].strftime("%Y-%m-%d %H:%M:%S")
        await message.reply_text(
            f"👋 Welcome!\n"
            f"✅ आपका token active है!\n"
            f"⏳ Valid till: {exp}\n\n"
            f"आप बिना ad देखे videos access कर सकते हैं!"
        )
        return

    # Create new token
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
    url = f"https://{HOST}/watch?data={encoded}"

    short_url = short_adrinolinks(url)

    await message.reply_text(
        f"🔗 आपका token activate करने के लिए नीचे ad देखें:\n\n{short_url}"
    )
