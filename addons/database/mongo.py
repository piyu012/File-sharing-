from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]

tokens_col = db.tokens
