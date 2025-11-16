from pyrogram import Client, filters
from db_init import ensure_ttl, has_pass, grant_pass, use_token
import os, time, hmac, hashlib

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BASE_URL = os.getenv("BASE_URL", "https://your-render.onrender.com")

def sign(p: str) -> str:
    return hmac.new(HMAC_SECRET, p.encode(), hashlib.sha256).hexdigest()

@Client.on_message(filters.command("start"))
async def start_gate(c, m):
    if await has_pass(m.from_user.id):
        return await m.reply_text("Access active. Use /genlink or /batch.")

    payload = f"{m.from_user.id}:{int(time.time())}"
    sig = sign(payload)
    watch = f"{BASE_URL}/watch?payload={payload}&sig={sig}"

    # FIXED MULTILINE STRING
    text = (
        f"Access locked.\n"
        f"Ad dekhkar token lo: {watch}\n"
        f"Ya token ho to /redeem TOKEN bhejo."
    )

    await m.reply_text(text)

@Client.on_message(filters.command("redeem"))
async def redeem(c, m):
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply_text("Format: /redeem TOKEN")

    hours = await use_token(parts[1], m.from_user.id)
    if not hours:
        return await m.reply_text("Token invalid ya expired.")

    await grant_pass(m.from_user.id, hours)
    await m.reply_text("Activation successful ✅ 24h access active.")
