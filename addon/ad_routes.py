import os
import hmac
import hashlib
import time
import base64
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from datetime import datetime
from db_init import tokens, has_valid_token, create_token, activate_token
from config import HMAC_SECRET, BASE_URL, BOT_USERNAME, ADRINO_API, OWNER_ID

router = APIRouter()

def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(long_url: str) -> str:
    if not ADRINO_API:
        return long_url
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}").json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

@router.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    doc = await tokens.find_one({"payload": payload, "sig": sig})
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
      <title>Loading...</title>
    </head>
    <body><h2>Please wait, processing...</h2></body>
    </html>
    """

@router.get("/callback")
async def callback(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid data")

    uid = await activate_token(payload, sig)
    if uid is None:
        raise HTTPException(403, "Token invalid or expired")

    # Notify user via bot
    from main import bot
    try:
        await bot.send_message(uid, "Token verified successfully! Valid for 12 hours.")
    except:
        pass

    # Notify admin
    try:
        await bot.send_message(OWNER_ID, f"Token activated by user {uid}")
    except:
        pass

    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=verified"
    return HTMLResponse(f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="0; url={deep_link}" />
      <title>Success!</title>
    </head>
    <body>
      <h2>Token Activated!</h2>
      <p>Redirecting to Telegram...</p>
      <a href="{deep_link}">Click here if not redirected</a>
    </body>
    </html>
    """)
