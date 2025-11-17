import os, hmac, hashlib, time, asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
api = FastAPI()

bot = Client(
    "adbot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH")),
    bot_token=BOT_TOKEN
)

def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

# ---------------- BOT START / STOP ----------------

@api.on_event("startup")
async def startup_event():
    print("Starting Pyrogram bot...")
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    print("Stopping Pyrogram bot...")
    await bot.stop()

# -------------------- BOT HANDLER --------------------

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text("👋 Welcome!\n\nClick /watch to earn tokens.")

# ------------------- FASTAPI ROUTES ------------------

@api.get("/watch", response_class=HTMLResponse)
async def watch(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    return f"""
    <html>
    <body>
      <h2>Watch Ad</h2>
      <p>Wait 6 seconds…</p>

      <script>
      setTimeout(function(){{
          window.location.href="/callback?payload={payload}&sig={sig}";
      }},6000);
      </script>
    </body>
    </html>
    """

@api.get("/callback")
async def callback(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
