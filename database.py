import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL, DB_NAME

# Motor async client
mongo_client = AsyncIOMotorClient(DB_URL)
database = mongo_client[DB_NAME]
user_data = database['users']

async def present_user(user_id: int):
    found = await user_data.find_one({'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    await user_data.insert_one({'_id': user_id})
    return

async def full_userbase():
    user_docs = user_data.find()
    user_ids = []
    async for doc in user_docs:
        user_ids.append(doc['_id'])
    return user_ids

async def del_user(user_id: int):
    await user_data.delete_one({'_id': user_id})
    return
