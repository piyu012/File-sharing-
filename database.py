from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

class Database:
    def __init__(self, uri):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client.file_sharing_bot
        self.users = self.db.users
        self.files = self.db.files
    
    async def add_user(self, user_id):
        """Add user to database if not exists"""
        existing = await self.users.find_one({"user_id": user_id})
        if not existing:
            await self.users.insert_one({
                "user_id": user_id,
                "joined_date": datetime.now(),
                "token_expiry": None,
                "is_banned": False
            })
    
    async def get_user(self, user_id):
        """Get user data"""
        return await self.users.find_one({"user_id": user_id})
    
    async def update_token(self, user_id, expiry_date):
        """Update or create user token"""
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "token_expiry": expiry_date,
                    "token_updated": datetime.now()
                }
            },
            upsert=True
        )
    
    async def check_token(self, user_id):
        """Check if user has valid token"""
        user = await self.get_user(user_id)
        if not user or not user.get('token_expiry'):
            return False
        
        if user['token_expiry'] < datetime.now():
            return False
        
        return True
    
    async def delete_expired_tokens(self):
        """Delete all expired tokens"""
        result = await self.users.update_many(
            {"token_expiry": {"$lt": datetime.now()}},
            {"$set": {"token_expiry": None}}
        )
        return result.modified_count
    
    async def get_all_users(self):
        """Get all users"""
        cursor = self.users.find({})
        return await cursor.to_list(length=None)
    
    async def get_stats(self):
        """Get bot statistics"""
        total_users = await self.users.count_documents({})
        active_tokens = await self.users.count_documents({
            "token_expiry": {"$gte": datetime.now()}
        })
        expired_tokens = await self.users.count_documents({
            "token_expiry": {"$lt": datetime.now(), "$ne": None}
        })
        total_files = await self.files.count_documents({})
        
        return {
            "total_users": total_users,
            "active_tokens": active_tokens,
            "expired_tokens": expired_tokens,
            "total_files": total_files
        }
    
    async def add_file(self, message_id, file_info):
        """Add file to database"""
        await self.files.insert_one({
            "message_id": message_id,
            "file_name": file_info.get('name'),
            "file_size": file_info.get('size'),
            "uploaded_date": datetime.now()
        })
    
    async def ban_user(self, user_id):
        """Ban user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_banned": True}}
        )
    
    async def unban_user(self, user_id):
        """Unban user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_banned": False}}
        )
