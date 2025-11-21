import os
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import Database
from config import *
import requests

# Initialize Bot
bot = Client(
    "FileShareBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

db = Database(DATABASE_URI)

# Helper Functions
def get_size(size):
    """Convert bytes to readable format"""
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units)-1:
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"

def shorten_url(long_url):
    """Shorten URL using link shortener API"""
    try:
        response = requests.post(
            SHORTENER_API_URL,
            json={"url": long_url},
            headers={"api-key": SHORTENER_API_KEY}
        )
        if response.status_code == 200:
            return response.json().get("short_url", long_url)
    except:
        pass
    return long_url

async def check_user_subscription(client, user_id):
    """Check if user is subscribed to force sub channels"""
    for channel_id in FORCE_SUB_CHANNELS:
        try:
            member = await client.get_chat_member(channel_id, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

async def generate_file_link(message_id):
    """Generate shareable link for file"""
    base_url = f"https://t.me/{BOT_USERNAME}?start=file_{message_id}"
    if ENABLE_SHORTENER:
        return shorten_url(base_url)
    return base_url

# Start Command
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    user_id = message.from_user.id
    
    # Add user to database
    await db.add_user(user_id)
    
    # Check if it's a file access link
    if len(message.text.split()) > 1:
        data = message.text.split(None, 1)[1]
        
        if data.startswith("file_"):
            # Check token
            token_valid = await db.check_token(user_id)
            if not token_valid:
                await message.reply_text(
                    "❌ **Token Required!**\n\n"
                    "Aapko is bot ka use karne ke liye token chahiye.\n"
                    f"Token ke liye contact karo: {ADMIN_USERNAME}\n\n"
                    "Ya neeche diye button se channel join karo:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNELS[0][1:]}")],
                        [InlineKeyboardButton("✅ Verify Token", callback_data="verify_token")]
                    ])
                )
                return
            
            # Check subscription
            is_subscribed = await check_user_subscription(client, user_id)
            if not is_subscribed:
                buttons = []
                for channel in FORCE_SUB_CHANNELS:
                    buttons.append([InlineKeyboardButton(
                        f"📢 Join Channel", 
                        url=f"https://t.me/{channel[1:]}"
                    )])
                buttons.append([InlineKeyboardButton("✅ Joined! Try Again", callback_data=f"check_{data}")])
                
                await message.reply_text(
                    "❌ **Subscription Required!**\n\n"
                    "Is bot ka use karne ke liye sabhi channels join karo:",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return
            
            # Send file
            file_id = int(data.split("_")[1])
            try:
                file_msg = await client.get_messages(DATABASE_CHANNEL, file_id)
                
                # Show ad before sending file
                if ENABLE_ADS:
                    await message.reply_text(
                        "📢 **Please wait...**\n\n"
                        f"File aane se pehle {AD_WAIT_TIME} seconds wait karo!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎯 Visit Ad", url=AD_LINK)]
                        ])
                    )
                    await asyncio.sleep(AD_WAIT_TIME)
                
                # Forward file
                await file_msg.copy(message.chat.id)
                await message.reply_text(
                    "✅ **File Sent Successfully!**\n\n"
                    f"Token Expiry: {(await db.get_user(user_id))['token_expiry'].strftime('%d-%m-%Y')}"
                )
                
            except Exception as e:
                await message.reply_text("❌ File not found!")
    
    else:
        # Welcome message
        await message.reply_text(
            f"👋 **Welcome {message.from_user.first_name}!**\n\n"
            "🤖 Main ek file sharing bot hoon.\n\n"
            "**Features:**\n"
            "• File upload & share with links\n"
            "• Token-based access system\n"
            "• Secure file storage\n\n"
            f"Token chahiye? Contact: {ADMIN_USERNAME}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNELS[0][1:]}")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
            ])
        )

# Admin Commands
@bot.on_message(filters.command("gentoken") & filters.user(ADMIN_IDS))
async def generate_token(client, message: Message):
    if len(message.command) < 3:
        await message.reply_text("Usage: `/gentoken user_id days`\nExample: `/gentoken 123456789 30`")
        return
    
    try:
        user_id = int(message.command[1])
        days = int(message.command[2])
        
        expiry = datetime.now() + timedelta(days=days)
        await db.update_token(user_id, expiry)
        
        await message.reply_text(
            f"✅ **Token Generated!**\n\n"
            f"User ID: `{user_id}`\n"
            f"Valid till: {expiry.strftime('%d-%m-%Y')}\n"
            f"Duration: {days} days"
        )
        
        # Notify user
        try:
            await bot.send_message(
                user_id,
                f"🎉 **Token Activated!**\n\n"
                f"Aapka token {days} days ke liye activate ho gaya hai.\n"
                f"Valid till: {expiry.strftime('%d-%m-%Y')}\n\n"
                "Ab aap bot ka use kar sakte ho!"
            )
        except:
            pass
            
    except ValueError:
        await message.reply_text("❌ Invalid format! User ID aur days numbers mein hone chahiye.")

@bot.on_message(filters.command("stats") & filters.user(ADMIN_IDS))
async def get_stats(client, message: Message):
    stats = await db.get_stats()
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"✅ Active Tokens: {stats['active_tokens']}\n"
        f"❌ Expired Tokens: {stats['expired_tokens']}\n"
        f"📁 Total Files: {stats['total_files']}"
    )

@bot.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_message(client, message: Message):
    if message.reply_to_message:
        users = await db.get_all_users()
        success = 0
        failed = 0
        
        status_msg = await message.reply_text("Broadcasting...")
        
        for user in users:
            try:
                await message.reply_to_message.copy(user['user_id'])
                success += 1
            except:
                failed += 1
            
            if (success + failed) % 10 == 0:
                await status_msg.edit_text(
                    f"Broadcasting...\n\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}"
                )
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete!**\n\n"
            f"Success: {success}\n"
            f"Failed: {failed}"
        )
    else:
        await message.reply_text("Reply to a message to broadcast!")

# File Upload Handler
@bot.on_message((filters.document | filters.video | filters.audio) & filters.user(ADMIN_IDS))
async def handle_file_upload(client, message: Message):
    # Forward to database channel
    forwarded = await message.copy(DATABASE_CHANNEL)
    
    # Generate link
    link = await generate_file_link(forwarded.id)
    
    # Get file info
    file = message.document or message.video or message.audio
    file_name = getattr(file, 'file_name', 'Unknown')
    file_size = get_size(file.file_size)
    
    await message.reply_text(
        f"✅ **File Uploaded Successfully!**\n\n"
        f"📁 Name: `{file_name}`\n"
        f"📦 Size: {file_size}\n"
        f"🔗 Link: `{link}`\n\n"
        "Share this link with users!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Copy Link", url=link)]
        ])
    )

# Batch File Upload
@bot.on_message(filters.command("batch") & filters.user(ADMIN_IDS))
async def batch_upload(client, message: Message):
    await message.reply_text(
        "📦 **Batch Mode Activated**\n\n"
        "Ab aap multiple files bhej sakte ho.\n"
        "Saari files ke links ek saath generate honge.\n\n"
        "Finish karne ke liye `/done` type karo."
    )
    
    batch_files = []
    
    @bot.on_message((filters.document | filters.video | filters.audio) & filters.user(message.from_user.id))
    async def collect_files(client, msg: Message):
        forwarded = await msg.copy(DATABASE_CHANNEL)
        batch_files.append({
            'id': forwarded.id,
            'name': getattr(msg.document or msg.video or msg.audio, 'file_name', 'Unknown')
        })
        await msg.reply_text(f"✅ File {len(batch_files)} added!")
    
    @bot.on_message(filters.command("done") & filters.user(message.from_user.id))
    async def finish_batch(client, msg: Message):
        if not batch_files:
            await msg.reply_text("❌ No files uploaded!")
            return
        
        links_text = "✅ **Batch Upload Complete!**\n\n"
        for i, file in enumerate(batch_files, 1):
            link = await generate_file_link(file['id'])
            links_text += f"{i}. `{file['name']}`\n   {link}\n\n"
        
        await msg.reply_text(links_text)

# Callback Query Handler
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "verify_token":
        token_valid = await db.check_token(user_id)
        if token_valid:
            await callback_query.answer("✅ Token valid hai!", show_alert=True)
        else:
            await callback_query.answer("❌ Token expired ya invalid!", show_alert=True)
    
    elif data.startswith("check_"):
        is_subscribed = await check_user_subscription(client, user_id)
        if is_subscribed:
            await callback_query.answer("✅ Subscription verified! Ab try karo.", show_alert=True)
        else:
            await callback_query.answer("❌ Abhi bhi subscribed nahi ho!", show_alert=True)
    
    elif data == "help":
        await callback_query.message.edit_text(
            "📚 **Help & Commands**\n\n"
            "**For Users:**\n"
            "• Send file link to access files\n"
            "• Token required for access\n"
            "• Join all channels to use\n\n"
            "**For Admins:**\n"
            "• `/gentoken user_id days` - Generate token\n"
            "• `/stats` - View bot statistics\n"
            "• `/broadcast` - Send message to all users\n"
            "• `/batch` - Upload multiple files\n"
            "• Send files directly to upload\n\n"
            f"Admin contact: {ADMIN_USERNAME}"
        )

# Auto-delete expired tokens (runs daily)
async def cleanup_expired_tokens():
    while True:
        await asyncio.sleep(86400)  # 24 hours
        deleted = await db.delete_expired_tokens()
        print(f"Cleaned up {deleted} expired tokens")

# Start Bot
async def main():
    await bot.start()
    print("✅ Bot started successfully!")
    
    # Start cleanup task
    asyncio.create_task(cleanup_expired_tokens())
    
    # Keep bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
