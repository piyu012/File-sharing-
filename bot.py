#(Â©)JishuDeveloper
# File Sharing Bot - Complete Single File
# Based on CodeXBotz/JishuDeveloper structure
# Added health check server for Render.com

import os
import sys
import asyncio
import base64
import logging
import time
from datetime import datetime
from typing import Union, Optional, List

# Pyrogram imports  
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant
from pyrogram.errors.exceptions.bad_request_400 import MessageEmpty

# MongoDB
from motor.motor_asyncio import AsyncIOMotorClient

# aiohttp for health check
from aiohttp import web

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s - %(levelname)s] - %(name)s - %(message)s',
    datefmt='%d-%b-%y %H:%M:%S'
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

class Config:
    # Bot settings
    API_HASH = os.environ.get("API_HASH", "")
    APP_ID = int(os.environ.get("APP_ID", "0"))
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # Channel settings  
    CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
    FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "0"))
    
    # Admin settings
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    ADMINS = []
    try:
        admin_list = os.environ.get("ADMINS", "")
        if admin_list:
            ADMINS = [int(x) for x in admin_list.split()]
    except:
        pass
    ADMINS.append(OWNER_ID)
    
    # Database
    DB_URL = os.environ.get("DB_URL", "")
    DB_NAME = os.environ.get("DB_NAME", "filesharexbot")
    
    # Port for health check (Render requirement)
    PORT = int(os.environ.get("PORT", "10000"))
    
    # Features
    PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False") == "True"
    FILE_AUTO_DELETE = int(os.environ.get("FILE_AUTO_DELETE", "0"))
    DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False") == "True"
    
    # Messages
    START_MESSAGE = os.environ.get("START_MESSAGE", 
        "<b>Hello {first} ðŸ‘‹\n\n"
        "I can store private files in Specified Channel and other users can access it from special link.</b>"
    )
    
    FORCE_SUB_MESSAGE = os.environ.get("FORCE_SUB_MESSAGE",
        "<b>Hello {first} ðŸ‘‹\n\n"
        "You need to join in my Channel/Group to use me\n\n"
        "Kindly Please join Channel</b>"
    )
    
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)
    BOT_STATS_TEXT = os.environ.get("BOT_STATS_TEXT", "<b>BOT UPTIME</b>\n{uptime}")
    USER_REPLY_TEXT = os.environ.get("USER_REPLY_TEXT", "âŒDon't send me messages directly I'm only File Share bot!")

# ============================================
# DATABASE
# ============================================

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users

    def new_user(self, id, name):
        return dict(id=id, name=name, join_date=datetime.now())

    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id': int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

# ============================================
# HELPER FUNCTIONS
# ============================================

async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = (base64_bytes.decode("ascii")).strip("=")
    return base64_string

async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes) 
    string = string_bytes.decode("ascii")
    return string

def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

async def is_subscribed(client, user_id):
    """Check if user subscribed to force sub channel"""
    if Config.FORCE_SUB_CHANNEL == 0:
        return True
    if user_id in Config.ADMINS:
        return True
    try:
        member = await client.get_chat_member(
            chat_id=Config.FORCE_SUB_CHANNEL,
            user_id=user_id
        )
        if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
            return True
        else:
            return False
    except UserNotParticipant:
        return False
    except Exception as e:
        LOGGER.error(f"Error checking subscription: {e}")
        return True

# ============================================
# HEALTH CHECK SERVER (Render.com requirement)
# ============================================

async def health_check(request):
    """Health check endpoint for Render"""
    return web.Response(text="Bot is running! âœ…", status=200)

async def start_health_server():
    """Start HTTP server on PORT"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    LOGGER.info(f"Health check server started on port {Config.PORT}")

# ============================================
# BOT INITIALIZATION
# ============================================

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="FileShareBot",
            api_id=Config.APP_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=10,
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        self.username = usr_bot_me.username
        
        # Verify database channel
        try:
            self.db_channel = await self.get_chat(Config.CHANNEL_ID)
            self.db_channel_username = self.db_channel.username if self.db_channel.username else None
        except Exception as e:
            self.LOGGER.error(f"Make sure bot is admin in DB channel. Error: {e}")
            sys.exit()
        
        # Initialize database
        self.db = Database(Config.DB_URL, Config.DB_NAME)
        
        # Start health check server
        await start_health_server()
        
        self.LOGGER.info(f"Bot Started as @{self.username}")

    async def stop(self, *args):
        await super().stop()
        self.LOGGER.info("Bot stopped!")

# Create bot instance
app = Bot()

# ============================================
# START COMMAND
# ============================================

@app.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # Add user to database
    if not await client.db.is_user_exist(user_id):
        await client.db.add_user(user_id, first_name)
        LOGGER.info(f"New user: {first_name} ({user_id})")
    
    # Check for file ID in command
    if len(message.command) != 2:
        # Normal start message
        buttons = [
            [InlineKeyboardButton("ðŸ“¢ Updates", url="https://t.me/JishuBotz")],
            [InlineKeyboardButton("ðŸ’¬ Support", url="https://t.me/JishuDeveloper")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await message.reply_text(
            text=Config.START_MESSAGE.format(
                first=first_name,
                last=message.from_user.last_name or "",
                username=f"@{message.from_user.username}" if message.from_user.username else "None",
                mention=message.from_user.mention,
                id=user_id
            ),
            reply_markup=reply_markup,
            quote=True
        )
        return
    
    # File share link
    base64_string = message.command[1]
    
    # Check force subscribe
    if Config.FORCE_SUB_CHANNEL != 0:
        if not await is_subscribed(client, user_id):
            try:
                invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
                buttons = [
                    [InlineKeyboardButton("ðŸ“¢ Join Channel", url=invite_link.invite_link)],
                    [InlineKeyboardButton("ðŸ”„ Try Again", callback_data=f"checksub_{base64_string}")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                
                await message.reply_text(
                    text=Config.FORCE_SUB_MESSAGE.format(
                        first=first_name,
                        last=message.from_user.last_name or "",
                        username=f"@{message.from_user.username}" if message.from_user.username else "None",
                        mention=message.from_user.mention,
                        id=user_id
                    ),
                    reply_markup=reply_markup,
                    quote=True
                )
                return
            except Exception as e:
                LOGGER.error(f"Error creating invite link: {e}")
    
    # Send files
    try:
        decoded_string = await decode(base64_string)
        file_ids = decoded_string.split("-")
        
        if len(file_ids) == 1:
            # Single file
            msg_id = int(file_ids[0])
            await send_single_file(client, message, msg_id)
        else:
            # Batch files  
            start_id = int(file_ids[0])
            end_id = int(file_ids[1])
            await send_batch_files(client, message, start_id, end_id)
            
    except Exception as e:
        LOGGER.error(f"Error decoding file ID: {e}")
        await message.reply_text("Invalid link!", quote=True)

async def send_single_file(client, message, msg_id):
    """Send single file to user"""
    try:
        msg = await client.get_messages(chat_id=Config.CHANNEL_ID, message_ids=msg_id)
        
        if not msg:
            await message.reply_text("File not found!", quote=True)
            return
        
        caption = msg.caption if msg.caption else ""
        
        # Custom caption
        if Config.CUSTOM_CAPTION and msg.document:
            caption = Config.CUSTOM_CAPTION.format(
                filename=msg.document.file_name if msg.document else "",
                previouscaption=caption
            )
        
        # Send file
        reply_markup = msg.reply_markup if not Config.DISABLE_CHANNEL_BUTTON else None
        
        sent_msg = await msg.copy(
            chat_id=message.from_user.id,
            caption=caption,
            protect_content=Config.PROTECT_CONTENT,
            reply_markup=reply_markup
        )
        
        # Auto delete
        if Config.FILE_AUTO_DELETE > 0:
            await asyncio.sleep(Config.FILE_AUTO_DELETE)
            try:
                await sent_msg.delete()
                await message.delete()
            except:
                pass
                
    except Exception as e:
        LOGGER.error(f"Error sending file: {e}")
        await message.reply_text(f"Error: {e}", quote=True)

async def send_batch_files(client, message, start_id, end_id):
    """Send batch files to user"""
    try:
        for msg_id in range(start_id, end_id + 1):
            try:
                msg = await client.get_messages(chat_id=Config.CHANNEL_ID, message_ids=msg_id)
                
                if not msg or msg.empty:
                    continue
                
                caption = msg.caption if msg.caption else ""
                
                # Custom caption
                if Config.CUSTOM_CAPTION and msg.document:
                    caption = Config.CUSTOM_CAPTION.format(
                        filename=msg.document.file_name if msg.document else "",
                        previouscaption=caption
                    )
                
                # Send file
                reply_markup = msg.reply_markup if not Config.DISABLE_CHANNEL_BUTTON else None
                
                await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    protect_content=Config.PROTECT_CONTENT,
                    reply_markup=reply_markup
                )
                
                await asyncio.sleep(1)  # Avoid flood
                
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                LOGGER.error(f"Error in batch: {e}")
                continue
        
        # Auto delete  
        if Config.FILE_AUTO_DELETE > 0:
            await asyncio.sleep(Config.FILE_AUTO_DELETE)
            try:
                await message.delete()
            except:
                pass
                
    except Exception as e:
        LOGGER.error(f"Error in batch: {e}")

# ============================================
# CALLBACK QUERY
# ============================================

@app.on_callback_query(filters.regex(r'^checksub_'))
async def check_subscription(client: Client, callback_query: CallbackQuery):
    """Check subscription callback"""
    user_id = callback_query.from_user.id
    base64_string = callback_query.data.split("_")[1]
    
    if not await is_subscribed(client, user_id):
        await callback_query.answer("âŒ You haven't joined yet!", show_alert=True)
        return
    
    await callback_query.answer("âœ… Subscription verified!", show_alert=True)
    await callback_query.message.delete()
    
    # Send files
    try:
        decoded_string = await decode(base64_string)
        file_ids = decoded_string.split("-")
        
        # Create dummy message
        class DummyMsg:
            def __init__(self, user):
                self.from_user = user
                self.chat = user
            async def reply_text(self, *args, **kwargs):
                pass
            async def delete(self):
                pass
        
        dummy_msg = DummyMsg(callback_query.from_user)
        
        if len(file_ids) == 1:
            msg_id = int(file_ids[0])
            await send_single_file(client, dummy_msg, msg_id)
        else:
            start_id = int(file_ids[0])
            end_id = int(file_ids[1])
            await send_batch_files(client, dummy_msg, start_id, end_id)
            
    except Exception as e:
        LOGGER.error(f"Error in callback: {e}")

# ============================================
# ADMIN COMMANDS
# ============================================

@app.on_message(filters.command('users') & filters.user(Config.ADMINS))
async def get_users(client: Client, message: Message):
    """Get total users"""
    total_users = await client.db.total_users_count()
    await message.reply_text(f"ðŸ‘¥ **Total Users:** {total_users}", quote=True)

@app.on_message(filters.command('broadcast') & filters.user(Config.ADMINS) & filters.reply)
async def broadcast(client: Client, message: Message):
    """Broadcast message to all users"""
    users = await client.db.get_all_users()
    broadcast_msg = message.reply_to_message
    
    total = 0
    success = 0
    failed = 0
    
    async for user in users:
        total += 1
        try:
            await broadcast_msg.copy(chat_id=user['id'])
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await broadcast_msg.copy(chat_id=user['id'])
            success += 1
        except Exception:
            failed += 1
    
    await message.reply_text(
        f"âœ… Broadcast completed!\n\n"
        f"Total: {total}\n"
        f"Success: {success}\n"
        f"Failed: {failed}",
        quote=True
    )

@app.on_message(filters.command('stats') & filters.user(Config.ADMINS))
async def stats(client: Client, message: Message):
    """Bot statistics"""
    uptime = get_readable_time((datetime.now() - client.uptime).seconds)
    stats_text = Config.BOT_STATS_TEXT.format(uptime=uptime)
    await message.reply_text(stats_text, quote=True)

@app.on_message(filters.command('batch') & filters.user(Config.ADMINS))
async def batch(client: Client, message: Message):
    """Generate batch link"""
    if len(message.command) < 3:
        await message.reply_text(
            "Usage:\n/batch [first_msg_id] [last_msg_id]\n\nExample: /batch 100 150",
            quote=True
        )
        return
    
    try:
        first_id = int(message.command[1])
        last_id = int(message.command[2])
        
        if first_id >= last_id:
            await message.reply_text("First ID must be less than last ID!", quote=True)
            return
        
        encoded = await encode(f"{first_id}-{last_id}")
        link = f"https://t.me/{client.username}?start={encoded}"
        
        await message.reply_text(
            f"âœ… **Batch Link Generated!**\n\n"
            f"**Total Messages:** {last_id - first_id + 1}\n"
            f"**Link:** `{link}`",
            quote=True
        )
    except Exception as e:
        await message.reply_text(f"Error: {e}", quote=True)

@app.on_message(filters.command('genlink') & filters.user(Config.ADMINS))
async def genlink(client: Client, message: Message):
    """Generate single file link"""
    if len(message.command) < 2:
        await message.reply_text(
            "Usage:\n/genlink [message_id]\n\nExample: /genlink 100",
            quote=True
        )
        return
    
    try:
        msg_id = int(message.command[1])
        encoded = await encode(str(msg_id))
        link = f"https://t.me/{client.username}?start={encoded}"
        
        await message.reply_text(
            f"âœ… **Link Generated!**\n\n"
            f"**Link:** `{link}`",
            quote=True
        )
    except Exception as e:
        await message.reply_text(f"Error: {e}", quote=True)

@app.on_message(filters.command('id'))
async def show_id(client: Client, message: Message):
    """Show user/chat ID"""
    text = f"ðŸ‘¤ **Your ID:** `{message.from_user.id}`\n"
    
    if message.chat.type != enums.ChatType.PRIVATE:
        text += f"ðŸ’¬ **Chat ID:** `{message.chat.id}`\n"
    
    if message.reply_to_message:
        text += f"ðŸ‘¤ **Replied User ID:** `{message.reply_to_message.from_user.id}`"
    
    await message.reply_text(text, quote=True)

# ============================================
# OTHER MESSAGES
# ============================================

@app.on_message(filters.private & filters.incoming)
async def handle_private_message(client: Client, message: Message):
    """Handle other private messages"""
    if message.text and message.text.startswith('/'):
        return
    
    await message.reply_text(Config.USER_REPLY_TEXT, quote=True)

# ============================================
# MAIN FUNCTION
# ============================================

if __name__ == "__main__":
    # Verify config
    if not Config.BOT_TOKEN:
        LOGGER.error("BOT_TOKEN not found!")
        sys.exit(1)
    
    if not Config.API_HASH or Config.APP_ID == 0:
        LOGGER.error("API_HASH or APP_ID not found!")
        sys.exit(1)
    
    if Config.CHANNEL_ID == 0:
        LOGGER.error("CHANNEL_ID not found!")
        sys.exit(1)
    
    if not Config.DB_URL:
        LOGGER.error("DB_URL not found!")
        sys.exit(1)
    
    # Run bot
    app.run()
