import os, hmac, hashlib, base64
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from main import api
from db_init import passes
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import HMAC_SECRET, DB_URL, DB_NAME, BOT_USERNAME

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
ad_tokens = db.ad_tokens

def sign(payload: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

@api.get("/watch", response_class=HTMLResponse)
async def watch_ad(payload: str, sig: str):
    expected_sig = sign(payload)
    if sig != expected_sig:
        raise HTTPException(400, "Invalid signature")
    
    now = datetime.utcnow()
    doc = await ad_tokens.find_one({"payload": payload})
    
    if doc and doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")
    if doc and doc["used"]:
        raise HTTPException(403, "Token already used")
    
    if not doc:
        expires = now + timedelta(hours=12)
        await ad_tokens.insert_one({"payload": payload, "sig": sig, "created_at": now, "expires_at": expires, "used": False})
    
    html = f'<html><head><meta http-equiv="refresh" content="0; url=/callback?payload={payload}&sig={sig}"/></head><body>Loading...</body></html>'
    return html

@api.get("/callback")
async def activate_token(payload: str, sig: str):
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
    
    uid_str, ts = payload.split(":")
    uid = int(uid_str)
    
    await ad_tokens.update_one({"_id": doc["_id"]}, {"$set": {"used": True, "activated_at": now}})
    
    valid_until = now + timedelta(hours=24)
    await passes.update_one({"user_id": uid}, {"$set": {"user_id": uid, "validUntil": valid_until}}, upsert=True)
    
    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=activated"
    html = f'<html><head><meta http-equiv="refresh" content="0; url={deep_link}"/></head><body>Success! Redirecting...</body></html>'
    return html

@api.on_event("startup")
async def startup_ad_system():
    await ad_tokens.create_index("expires_at", expireAfterSeconds=0)
    print("[AD SYSTEM] Ad routes initialized")
