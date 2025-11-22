import os
import sys
import asyncio
import datetime
import logging
import base64
import httpx
import secrets

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
class Config:
    API_HASH = os.environ.get("API_HASH", "")
    APP_ID = int(os.environ.get("APP_ID", "0"))
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

    DB_URL = os.environ.get("DB_URL", "")
    DB_NAME = os.environ.get("DB_NAME", "FileSharingBot")

    PORT = int(os.environ.get("PORT", "10000"))
    PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False").lower() == "true"
    FILE_AUTO_DELETE = int(os.environ.get("FILE_AUTO_DELETE", "600"))

    START_MESSAGE = os.environ.get("START_MESSAGE", "<b>Hi {mention}! Welcome to the File Sharing Bot.</b>")
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "")

    TOKEN_VALID_HOURS = int(os.environ.get("TOKEN_VALID_HOURS", "12"))
    
    # Adrinolinks Configuration
    ADRINOLINKS_API_KEY = os.environ.get("ADRINOLINKS_API_KEY", "")
    ADRINOLINKS_BASE = "https://adrinolinks.in/api"
    
    # Your deployed app URL (à¤†à¤ªà¤•à¤¾ Render URL)
    APP_URL = os.environ.get("APP_URL", "https://file-sharing-yw4r.onrender.com")

# ---------------- DATABASE ----------------
class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db['users']
        self.files = self.db['file_ids']
        self.verify_tokens = self.db['verify_tokens']

    async def add_user(self, user_id, first_name, username):
        await self.users.update_one(
            {'id': user_id},
            {'$set': {'id': user_id, 'first_name': first_name, 'username': username, 'join_date': datetime.datetime.utcnow()}},
            upsert=True
        )

    async def add_file(self, file_id, unique_id, caption=None):
        await self.files.insert_one({'file_id': file_id, 'unique_id': unique_id, 'caption': caption})

    async def set_token(self, user_id, hours=Config.TOKEN_VALID_HOURS):
        expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        await self.users.update_one({'id': user_id}, {'$set': {'token_expiry': expiry}}, upsert=True)
        return expiry

    async def is_token_valid(self, user_id):
        user = await self.users.find_one({'id': user_id})
        return user and 'token_expiry' in user and datetime.datetime.utcnow() < user['token_expiry']

    async def create_verify_token(self, user_id):
        """Create a unique verification token for ad completion"""
        token = secrets.token_urlsafe(32)
        await self.verify_tokens.insert_one({
            'token': token,
            'user_id': user_id,
            'created_at': datetime.datetime.utcnow(),
            'used': False
        })
        return token

    async def verify_and_use_token(self, token):
        """Verify token and mark as used"""
        result = await self.verify_tokens.find_one({'token': token, 'used': False})
        if result:
            # Check if token is not too old (24 hours max)
            if datetime.datetime.utcnow() - result['created_at'] < datetime.timedelta(hours=24):
                await self.verify_tokens.update_one({'token': token}, {'$set': {'used': True}})
                return result['user_id']
        return None

# ---------------- UTILS ----------------
def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += "=" * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

async def generate_ad_link(user_id: int, db: Database) -> str:
    """Generate adrinolinks short link with proper verification flow"""
    try:
        # Step 1: Create unique verification token
        verify_token = await db.create_verify_token(user_id)
        
        # Step 2: Create verification URL (à¤¯à¤¹ URL ad complete à¤¹à¥‹à¤¨à¥‡ à¤•à¥‡ à¤¬à¤¾à¤¦ à¤–à¥à¤²à¥‡à¤—à¤¾)
        verify_url = f"{Config.APP_URL}/verify?token={verify_token}"
        
        # Step 3: Shorten verification URL through adrinolinks
        async with httpx.AsyncClient(timeout=15) as client:
            params = {
                "api": Config.ADRINOLINKS_API_KEY,
                "url": verify_url
            }
            resp = await client.get(Config.ADRINOLINKS_BASE, params=params)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Check different response formats
                if data.get("status") == "success" and "shortenedUrl" in data:
                    return data["shortenedUrl"]
                elif "shortenedUrl" in data:
                    return data["shortenedUrl"]
                elif "shortened" in data:
                    return data["shortened"]
                elif "shorturl" in data:
                    return data["shorturl"]
                else:
                    logger.error(f"Unexpected adrinolinks response: {data}")
                    return verify_url
            else:
                logger.error(f"Adrinolinks API error: {resp.status_code} - {resp.text}")
                return verify_url
                
    except Exception as e:
        logger.error(f"Ad link generation error: {e}")
        return verify_url

# ---------------- BOT SETUP ----------------
Bot = Client("FileShareBot", api_id=Config.APP_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, workers=50)
db = Database(Config.DB_URL, Config.DB_NAME)

# ---------------- WEB SERVER ----------------
async def health_check(request):
    return web.Response(text="Bot is running! âœ…", status=200)

async def verify_handler(request):
    """Handle verification after ad is completed"""
    try:
        token = request.query.get("token")
        
        if not token:
            return web.Response(
                text="âŒ Invalid verification link!",
                status=400,
                content_type="text/html"
            )
        
        # Verify token and get user_id
        user_id = await db.verify_and_use_token(token)
        
        if user_id:
            # Activate user token
            expiry = await db.set_token(user_id)
            
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Token Activated</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }}
                    .success-icon {{
                        font-size: 60px;
                        color: #4CAF50;
                    }}
                    h1 {{
                        color: #333;
                        margin: 20px 0;
                    }}
                    p {{
                        color: #666;
                        line-height: 1.6;
                    }}
                    .btn {{
                        display: inline-block;
                        margin-top: 20px;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                    }}
                    .btn:hover {{
                        background: #5568d3;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">âœ…</div>
                    <h1>Token Activated!</h1>
                    <p>à¤†à¤ªà¤•à¤¾ token à¤¸à¤«à¤²à¤¤à¤¾à¤ªà¥‚à¤°à¥à¤µà¤• activate à¤¹à¥‹ à¤—à¤¯à¤¾ à¤¹à¥ˆà¥¤</p>
                    <p>Valid for: <strong>{Config.TOKEN_VALID_HOURS} hours</strong></p>
                    <a href="https://t.me/{(await Bot.get_me()).username}" class="btn">Return to Bot</a>
                </div>
            </body>
            </html>
            """
            
            # Try to notify user on Telegram
            try:
                await Bot.send_message(
                    user_id,
                    f"âœ… **Token Activated Successfully!**\n\n"
                    f"Your token is valid for **{Config.TOKEN_VALID_HOURS} hours**.\n"
                    f"You can now access files. Send /start to continue."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            return web.Response(
                text=html_response,
                status=200,
                content_type="text/html"
            )
        else:
            html_error = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Invalid Token</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    .error-icon {
                        font-size: 60px;
                        color: #f5576c;
                    }
                    h1 {
                        color: #333;
                        margin: 20px 0;
                    }
                    p {
                        color: #666;
                        line-height: 1.6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">âŒ</div>
                    <h1>Invalid or Expired Token</h1>
                    <p>à¤¯à¤¹ verification link à¤…à¤®à¤¾à¤¨à¥à¤¯ à¤¹à¥ˆ à¤¯à¤¾ à¤ªà¤¹à¤²à¥‡ à¤¸à¥‡ à¤‰à¤ªà¤¯à¥‹à¤— à¤•à¤¿à¤¯à¤¾ à¤œà¤¾ à¤šà¥à¤•à¤¾ à¤¹à¥ˆà¥¤</p>
                    <p>à¤•à¥ƒà¤ªà¤¯à¤¾ bot à¤ªà¤° à¤œà¤¾à¤•à¤° à¤¨à¤¯à¤¾ token generate à¤•à¤°à¥‡à¤‚à¥¤</p>
                </div>
            </body>
            </html>
            """
            return web.Response(
                text=html_error,
                status=400,
                content_type="text/html"
            )
            
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return web.Response(
            text=f"âŒ Server Error: {e}",
            status=500,
            content_type="text/html"
        )

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/verify', verify_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Health server running on port {Config.PORT}")

# ---------------- SEND FILE ----------------
async def send_file(client, user, encoded_file_id: str):
    try:
        decoded_id = int(decode_file_id(encoded_file_id))
        msg = await client.get_messages(Config.CHANNEL_ID, decoded_id)
        if not msg:
            await client.send_message(user.id, "âŒ File not found.")
            return
        
        caption = Config.CUSTOM_CAPTION or msg.caption
        await msg.copy(chat_id=user.id, caption=caption, protect_content=Config.PROTECT_CONTENT)
        
        # Auto delete after specified time
        if Config.FILE_AUTO_DELETE > 0:
            await asyncio.sleep(Config.FILE_AUTO_DELETE)
            try:
                await client.delete_messages(user.id, msg.id)
            except:
                pass
                
    except Exception as e:
        await client.send_message(user.id, f"âŒ Error: {e}")

# ---------------- OWNER AUTO LINK ----------------
@Bot.on_message(filters.private & filters.user(Config.OWNER_ID))
async def owner_auto_link(client, message: Message):
    # Ignore commands
    if message.text and message.text.startswith('/'):
        return
    
    ftype = "document" if message.document else "video" if message.video else "photo" if message.photo else "unknown"
    if ftype == "unknown":
        return
    
    # Copy to channel
    sent_msg = await message.copy(chat_id=Config.CHANNEL_ID)
    
    # Get file info
    if sent_msg.document:
        file_id = sent_msg.document.file_id
        unique_id = sent_msg.document.file_unique_id
    elif sent_msg.video:
        file_id = sent_msg.video.file_id
        unique_id = sent_msg.video.file_unique_id
    elif sent_msg.photo:
        file_id = sent_msg.photo.file_id
        unique_id = sent_msg.photo.file_unique_id
    else:
        return
    
    await db.add_file(file_id, unique_id, sent_msg.caption)
    
    # Generate share link
    encoded = encode_file_id(str(sent_msg.id))
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={encoded}"
    
    await message.reply_text(
        f"âœ… **File Uploaded Successfully!**\n\n"
        f"ðŸ“ **File Type:** {ftype.title()}\n"
        f"ðŸ”— **Share Link:**\n`{share_link}`",
        quote=True
    )

# ---------------- START COMMAND ----------------
@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    # Add user to database
    await db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

    # Owner doesn't need token
    if message.from_user.id == Config.OWNER_ID:
        await message.reply_text(
            "ðŸ‘‘ **Hi Owner!**\n\n"
            "Upload any file and I'll generate a shareable link for you.",
            quote=True
        )
        return

    # Check token validity
    valid = await db.is_token_valid(message.from_user.id)
    
    if not valid:
        ad_url = await generate_ad_link(message.from_user.id, db)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸ”„ Activate Token", url=ad_url)]
        ])
        await message.reply_text(
            "âŒ **Token Expired!**\n\n"
            "à¤†à¤ªà¤•à¤¾ token expire à¤¹à¥‹ à¤šà¥à¤•à¤¾ à¤¹à¥ˆà¥¤ File access à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:\n\n"
            "1ï¸âƒ£ à¤¨à¥€à¤šà¥‡ à¤¦à¤¿à¤ à¤—à¤ button à¤ªà¤° click à¤•à¤°à¥‡à¤‚\n"
            "2ï¸âƒ£ Ad à¤ªà¥‚à¤°à¤¾ à¤¦à¥‡à¤–à¥‡à¤‚\n"
            "3ï¸âƒ£ Token automatically activate à¤¹à¥‹ à¤œà¤¾à¤à¤—à¤¾\n\n"
            f"Token validity: **{Config.TOKEN_VALID_HOURS} hours**",
            reply_markup=keyboard,
            quote=True
        )
        return

    # Token is valid
    if len(message.command) > 1:
        # User is trying to access a file
        await send_file(client, message.from_user, message.command[1])
    else:
        # Just /start command
        text = Config.START_MESSAGE.format(mention=message.from_user.mention)
        await message.reply_text(
            f"âœ… **Token Active!**\n\n"
            f"Your token is valid for **{Config.TOKEN_VALID_HOURS} hours**.\n\n"
            f"{text}",
            quote=True
        )

# ---------------- STATS COMMAND (Owner only) ----------------
@Bot.on_message(filters.command("stats") & filters.user(Config.OWNER_ID))
async def stats_command(client, message: Message):
    total_users = await db.users.count_documents({})
    total_files = await db.files.count_documents({})
    active_tokens = await db.users.count_documents({
        'token_expiry': {'$gt': datetime.datetime.utcnow()}
    })
    
    await message.reply_text(
        f"ðŸ“Š **Bot Statistics**\n\n"
        f"ðŸ‘¥ Total Users: **{total_users}**\n"
        f"ðŸ“ Total Files: **{total_files}**\n"
        f"âœ… Active Tokens: **{active_tokens}**",
        quote=True
    )

# ---------------- MAIN ----------------
async def main():
    await start_health_server()
    await Bot.start()
    me = await Bot.get_me()
    logger.info(f"Bot started as @{me.username}")
    logger.info("âœ… Owner upload enabled")
    logger.info("âœ… Token system with adrinolinks verification enabled")
    logger.info(f"âœ… Token validity: {Config.TOKEN_VALID_HOURS} hours")
    await asyncio.Event().wait()

if __name__ == "__main__":
    required_vars = [
        "BOT_TOKEN", "API_HASH", "APP_ID", "CHANNEL_ID", 
        "DB_URL", "ADRINOLINKS_API_KEY", "APP_URL"
    ]
    
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped!")
