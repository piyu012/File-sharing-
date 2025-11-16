import os, hmac, hashlib, time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from aiogram import Bot
from db_init import mint_token

HMAC_SECRET = os.getenv("HMAC_SECRET","secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL","http://localhost:8000")
bot = Bot(BOT_TOKEN)

def sign(p:str)->str: return hmac.new(HMAC_SECRET, p.encode(), hashlib.sha256).hexdigest()

api = FastAPI()

@api.get("/watch", response_class=HTMLResponse)
async def watch(payload:str, sig:str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "bad sig")
    # Embed rewarded ad here; for demo produce a Claim button
    return HTMLResponse(f"""
    <html><body>
      <h3>Rewarded Ad</h3>
      <button onclick="fetch('/ad/callback?payload={payload}&sig={sig}')">Claim</button>
    </body></html>""")

@api.get("/ad/callback")
async def callback(payload:str, sig:str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "bad sig")
    uid, ts = payload.split(":")
    tok = await mint_token(int(uid))
    try:
        await bot.send_message(int(uid), f"Your token: {tok}
Use: /redeem {tok} (valid 6h)")
    except Exception:
        pass
    return {"ok": True}
