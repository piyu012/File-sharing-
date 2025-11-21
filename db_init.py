from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta

mongo = AsyncIOMotorClient(os.getenv("DB_URL"))
db = mongo[os.getenv("DB_NAME", "filesharebott")]

tokens = db.tokens
users = db.users

async def ensure_ttl():
    await tokens.create_index("expires_at", expireAfterSeconds=0)

async def has_valid_token(uid: int) -> bool:
    now = datetime.utcnow()
    doc = await tokens.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })
    return bool(doc)

async def create_token(uid: int, payload: str, sig: str, expire_hours: int = 12):
    now = datetime.utcnow()
    expire_time = now + timedelta(hours=expire_hours)
    
    await tokens.insert_one({
        "uid": uid,
        "payload": payload,
        "sig": sig,
        "created_at": now,
        "used": False,
        "activated_at": None,
        "expires_at": expire_time
    })

async def activate_token(uid: int, payload: str, sig: str):
    now = datetime.utcnow()
    
    result = await tokens.update_one(
        {
            "uid": uid,
            "payload": payload,
            "sig": sig,
            "used": False
        },
        {
            "$set": {
                "used": True,
                "activated_at": now
            }
        }
    )
    
    if result.modified_count == 0:
        raise Exception("Token not found or already activated")
    
    return True

async def add_user(uid: int):
    await users.insert_one({"uid": uid, "joined_at": datetime.utcnow()})

async def present_user(uid: int) -> bool:
    doc = await users.find_one({"uid": uid})
    return bool(doc)

async def full_userbase():
    cursor = users.find({})
    return [doc["uid"] async for doc in cursor]

async def del_user(uid: int):
    await users.delete_one({"uid": uid})
