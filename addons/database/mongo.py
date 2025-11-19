from motor.motor_asyncio import AsyncIOMotorClient
from addons.config import MONGO_URI, DB_NAME

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]

tokens_col = db.tokens
