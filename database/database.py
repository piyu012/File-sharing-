from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL, DB_NAME

# Mongo async client
dbclient = AsyncIOMotorClient(DB_URL)
database = dbclient[DB_NAME]
user_data = database["users"]


# ------------------ Check Present User ------------------ #
async def present_user(user_id: int) -> bool:
    found = await user_data.find_one({"_id": user_id})
    return bool(found)


# ------------------ Add User ------------------ #
async def add_user(user_id: int):
    await user_data.update_one(
        {"_id": user_id},
        {"$set": {"_id": user_id}},
        upsert=True
    )


# ------------------ Full User Base ------------------ #
async def full_userbase() -> list:
    cursor = user_data.find({})
    return [doc["_id"] async for doc in cursor]


# ------------------ Delete User ------------------ #
async def del_user(user_id: int):
    await user_data.delete_one({"_id": user_id})
