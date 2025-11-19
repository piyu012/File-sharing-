from motor.motor_asyncio import AsyncIOMotorClient
import os, datetime as dt, hashlib, time
from typing import Optional

mongo = AsyncIOMotorClient(os.getenv("DB_URL"))
db = mongo[os.getenv("DB_NAME", "filesharebott")]

# Collections
tokens = db.tokens
passes = db.passes
users = db.users

# ========== TTL INDEXES ==========
async def ensure_ttl():
    await tokens.create_index("expiresAt", expireAfterSeconds=0)
    await passes.create_index("validUntil", expireAfterSeconds=0)

# ========== TOKEN SYSTEM ==========
async def has_pass(uid: int) -> bool:
    now = dt.datetime.utcnow()
    doc = await passes.find_one({"user_id": uid, "validUntil": {"$gt": now}})
    return bool(doc)

async def grant_pass(uid: int, hours: int = 24):
    now = dt.datetime.utcnow()
    valid = now + dt.timedelta(hours=hours)
    await passes.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "validUntil": valid}},
        upsert=True
    )

async def mint_token(uid: int, hours: int = 24, redeem_window_hours: int = 6) -> str:
    tok = hashlib.sha1(f"{uid}:{time.time()}:{os.urandom(8)}".encode()).hexdigest()[:20]
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(hours=redeem_window_hours)
    await tokens.insert_one({
        "token": tok,
        "user_id": uid,
        "expiresAt": exp,
        "used": False,
        "pass_hours": hours
    })
    return tok

async def use_token(tok: str, uid: int) -> Optional[int]:
    doc = await tokens.find_one({"token": tok, "used": False})
    if not doc:
        return None
    if doc["user_id"] != uid:
        return None
    now = dt.datetime.utcnow()
    if doc["expiresAt"] < now:
        return None
    await tokens.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
    return doc["pass_hours"]

# ========== USER TRACKING ==========
async def present_user(user_id: int) -> bool:
    found = await users.find_one({'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    await users.insert_one({'_id': user_id})

async def full_userbase():
    user_docs = users.find()
    user_ids = []
    async for doc in user_docs:
        user_ids.append(doc['_id'])
    return user_ids

async def del_user(user_id: int):
    await users.delete_one({'_id': user_id})
