import os, hmac, hashlib, time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
api = FastAPI()

bot = Client(
    "adbot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=BOT_TOKEN
)

def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

@api.get("/watch", response_class=HTMLResponse)
async def watch(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    return HTMLResponse(f"""
    <html>
    <body>
      <h2>Watch Ad</h2>
      <p>Please wait 6 seconds…</p>

      <script>
      setTimeout(function(){{
          window.location.href="/callback?payload={payload}&sig={sig}";
      }},6000);
      </script>
    </body>
    </html>
    """)

@api.get("/callback")
async def callback(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    async with bot:
        await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
