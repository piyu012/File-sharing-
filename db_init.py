from motor.motor_asyncio import AsyncIOMotorClient
import os, datetime as dt, hashlib, time, os as _os
from typing import Optional   # <-- IMPORTANT for Python 3.8

mongo = AsyncIOMotorClient(os.getenv("DB_URL"))
db = mongo[os.getenv("DB_NAME", "fileshare")]
tokens = db.tokens
passes = db.passes

async def ensure_ttl():
    await tokens.create_index("expiresAt", expireAfterSeconds=0)
    await passes.create_index("validUntil", expireAfterSeconds=0)

async def has_pass(uid:int) -> bool:
    now = dt.datetime.utcnow()
    doc = await passes.find_one({"user_id": uid, "validUntil": {"$gt": now}})
    return bool(doc)

async def grant_pass(uid:int, hours:int=24):
    now = dt.datetime.utcnow()
    valid = now + dt.timedelta(hours=hours)
    await passes.update_one({"user_id": uid},
                            {"$set": {"user_id": uid, "validUntil": valid}},
                            upsert=True)

async def mint_token(uid:int, hours:int=24, redeem_window_hours:int=6) -> str:
    tok = hashlib.sha1(f"{uid}:{time.time()}:{_os.urandom(8)}".encode()).hexdigest()[:20]
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(hours=redeem_window_hours)
    await tokens.insert_one({
        "token": tok,
        "user_id": uid,
        "hours": hours,
        "createdAt": now,
        "expiresAt": exp
    })
    return tok

async def use_token(tok: str, uid: int) -> Optional[int]:  # <-- FIXED
    doc = await tokens.find_one({"token": tok})
    if not doc:
        return None
    await tokens.delete_one({"_id": doc["_id"]})
    return int(doc.get("hours", 24))
