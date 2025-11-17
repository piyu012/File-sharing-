from fastapi import FastAPI, HTTPException
from pyrogram import Client
import hmac, os, time

api = FastAPI()
bot = Client(...)  # Your bot instance here
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()

# HMAC sign function
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET, data.encode(), "sha256").hexdigest()

@api.get("/callback")
async def callback(payload: str = None, sig: str = None):
    # Missing query params
    if not payload or not sig:
        return {"error": "Invalid or missing parameters. Use the bot link."}

    # Invalid signature
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    # Extract user ID and timestamp
    try:
        uid, ts = payload.split(":")
        uid = int(uid)
    except:
        return {"error": "Invalid payload format."}

    # Generate token (example)
    token = str(int(time.time()))

    # Send token to user via bot
    try:
        await bot.send_message(uid, f"🎉 Your Token:\n\n`{token}`")
    except Exception as e:
        return {"error": f"Bot failed to send message: {str(e)}"}

    return {"ok": True, "token": token}
