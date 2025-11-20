from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta
from typing import Optional

mongo = AsyncIOMotorClient(os.getenv("DB_URL"))
db = mongo[os.getenv("DB_NAME", "filesharebott")]

# Collections
tokens = db.tokens
users = db.users

# ========== TTL INDEXES ==========
async def ensure_ttl():
    await tokens.create_index("expires_at", expireAfterSeconds=0)

# ========== TOKEN SYSTEM ==========
async def has_valid_token(uid: int) -> bool:
    """Check if user has active token"""
    now = datetime.utcnow()
    doc = await tokens.find_one({
        "uid": uid,
        "used": True,
        "expires_at": {"$gt": now}
    })
    return bool(doc)

async def create_token(uid: int, payload: str, sig: str, expire_hours: int = 12):
    """Create new token"""
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

async def activate_token(payload: str, sig: str) -> Optional[int]:
    """Activate token and return user ID"""
    doc = await tokens.find_one({"payload": payload, "sig": sig})
    if not doc:
        return None
    
    now = datetime.utcnow()
    if doc["expires_at"] < now or doc["used"]:
        return None
    
    uid = int(payload.split(":")[0])
    new_expiry = now + timedelta(hours=12)
    
    await tokens.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "used": True,
                "activated_at": now,
                "expires_at": new_expiry
            }
        }
    )
    return uid

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
