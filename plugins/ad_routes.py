
import os, hmac, hashlib, base64
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from main import api
from db_init import passes, ensure_ttl
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import HMAC_SECRET, DB_URL, DB_NAME, BOT_USERNAME

# MongoDB for ad tokens
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
ad_tokens = db.ad_tokens

# Initialize TTL
async def init_ad_ttl():
    await ad_tokens.create_index("expires_at", expireAfterSeconds=0)

def sign(payload: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

# ========== WATCH AD PAGE ==========
@api.get("/watch", response_class=HTMLResponse)
async def watch_ad(payload: str, sig: str):
    print(f"[AD] /watch called with payload={payload}")
    
    # Verify signature
    expected_sig = sign(payload)
    if sig != expected_sig:
        raise HTTPException(400, "Invalid signature")
    
    # Check if token exists and not expired
    doc = await ad_tokens.find_one({"payload": payload})
    now = datetime.utcnow()
    
    if doc:
        if doc["expires_at"] < now:
            raise HTTPException(403, "Token expired")
        if doc["used"]:
            raise HTTPException(403, "Token already used")
    else:
        # Create new token
        expires = now + timedelta(hours=12)
        await ad_tokens.insert_one({
            "payload": payload,
            "sig": sig,
            "created_at": now,
            "expires_at": expires,
            "used": False
        })
    
    # Redirect to callback (simulate ad watch)
    return f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/callback?payload={payload}&sig={sig}" />
        <title>Loading...</title>
    </head>
    <body>
        <h2>Please wait, processing...</h2>
    </body>
    </html>
    """

# ========== CALLBACK (TOKEN ACTIVATION) ==========
@api.get("/callback")
async def activate_token(payload: str, sig: str):
    print(f"[AD] /callback called with payload={payload}")
    
    # Verify signature
    expected_sig = sign(payload)
    if sig != expected_sig:
        raise HTTPException(400, "Invalid signature")
    
    doc = await ad_tokens.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")
    
    now = datetime.utcnow()
    if doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")
    if doc["used"]:
        raise HTTPException(403, "Token already used")
    
    # Extract user_id from payload
    uid_str, ts = payload.split(":")
    uid = int(uid_str)
    
    # Mark token as used
    await ad_tokens.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "activated_at": now}}
    )
    
    # Grant 24h pass
    valid_until = now + timedelta(hours=24)
    await passes.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "validUntil": valid_until}},
        upsert=True
    )
    
    print(f"[AD] Token activated for user {uid}")
    
    # Redirect to Telegram bot
    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=activated"
    return HTMLResponse(f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url={deep_link}" />
        <title>Success!</title>
    </head>
    <body>
        <h2>✅ Token Activated!</h2>
        <p>Redirecting to Telegram...</p>
        <a href="{deep_link}">Click here if not redirected</a>
    </body>
    </html>
    """)

# Initialize on startup
@api.on_event("startup")
async def startup_ad_system():
    await init_ad_ttl()
    print("[AD SYSTEM] Ad routes initialized")
