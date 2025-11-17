import os, hmac, hashlib, time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from aiogram import Bot
from db_init import mint_token

# ====== ENV CONFIG ======
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

bot = Bot(BOT_TOKEN)

# ====== SIGNATURE FUNCTION ======
def sign(p: str) -> str:
    return hmac.new(HMAC_SECRET, p.encode(), hashlib.sha256).hexdigest()

# ====== FASTAPI APP ======
api = FastAPI()

# -------------------------
# Ad Watch Page
# -------------------------
@api.get("/watch", response_class=HTMLResponse)
async def watch(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "bad signature")

    # Simple reward page
    return HTMLResponse(f"""
    <html>
    <body>
      <h2>Watch Ad to Claim Token</h2>
      <button onclick="fetch('/ad/callback?payload={payload}&sig={sig}')
        .then(r=>alert('Token sent to your Telegram!'))">
        Claim Reward
      </button>
    </body>
    </html>
    """)


# -------------------------
# Ad Callback (after watching ad)
# -------------------------
@api.get("/ad/callback")
async def callback(payload: str, sig: str):

    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "bad signature")

    uid, ts = payload.split(":")

    # Mint new token for this user
    tok = await mint_token(int(uid))

    # Send token to user
    try:
        await bot.send_message(
            int(uid),
            f"🎁 Your Token: {tok}\nUse: /redeem {tok} (valid for 6 hours)"
        )
    except Exception:
        pass

    return {"ok": True, "token": tok}
