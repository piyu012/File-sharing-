import os
import time
import hmac
import hashlib
import asyncio
import base64
import logging
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import (
    ADMINS, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL
)
from helper_func import subscribed, encode, decode, get_messages
from db_init import add_user, del_user, full_userbase, present_user, has_valid_token, create_token

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# TOKEN SIGNING
# ------------------------------
def sign(data: str) -> str:
    """Generate HMAC signature for token"""
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()

# ------------------------------
# SHORT LINK (ADRINOLINKS)
# ------------------------------
def short_adrinolinks(long_url: str) -> str:
    """Shorten URL using Adrinolinks API"""
    from config import ADRINO_API
    import requests
    
    if not ADRINO_API:
        return long_url
    
    try:
        response = requests.get(
            f"https://adrinolinks.com/api",
            params={'api': ADRINO_API, 'url': long_url},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return data.get('shortenedUrl', long_url)
    except Exception as e:
        logger.error(f"Adrinolinks error: {e}")
    
    return long_url

# ------------------------------
# AUTO DELETE FUNCTION
# ------------------------------
async def delete_file_later(client: Bot, message: Message, delay: int):
    """Delete message after specified delay"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        logger.info(f"Auto-deleted message {message.id}")
    except Exception as e:
        logger.error(f"Failed to auto-delete message: {e}")

# ------------------------------
# START COMMAND HANDLER
# ------------------------------
@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id
    
    # Add user to database if not present
    if not await present_user(uid):
        try:
            await add_user(uid)
            logger.info(f"New user added: {uid}")
        except Exception as e:
            logger.error(f"Failed to add user {uid}: {e}")
    
    # ------------------------------
    # HANDLE FILE LINK CLICKS
    # ------------------------------
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            logger.info(f"Received base64 string: {base64_string[:20]}...")
        except IndexError:
            await message.reply_text("❌ Invalid link format!")
            return
        
        # Decode the file ID(s)
        try:
            string = await decode(base64_string)
            logger.info(f"Decoded string: {string}")
            argument = string.split("-")
            
            # Handle batch request (multiple files)
            if len(argument) == 3:
                try:
                    start_id = int(int(argument[1]) / abs(client.db_channel.id))
                    end_id = int(int(argument[2]) / abs(client.db_channel.id))
                    logger.info(f"Batch request: {start_id} to {end_id}")
                except ValueError:
                    await message.reply_text("❌ Invalid batch link!")
                    return
                
                # Generate ID list
                if start_id <= end_id:
                    ids = range(start_id, end_id + 1)
                else:
                    ids = []
                    i = start_id
                    while True:
                        ids.append(i)
                        i -= 1
                        if i < end_id:
                            break
            
            # Handle single file request
            elif len(argument) == 2:
                try:
                    ids = [int(int(argument[1]) / abs(client.db_channel.id))]
                    logger.info(f"Single file request: {ids[0]}")
                except ValueError:
                    await message.reply_text("❌ Invalid file link!")
                    return
            else:
                await message.reply_text("❌ Invalid link format!")
                return
                
        except Exception as e:
            logger.error(f"Decode error: {e}")
            await message.reply_text("❌ Invalid or corrupted link!")
            return
        
        # ------------------------------
        # TOKEN VERIFICATION
        # ------------------------------
        if not await has_valid_token(uid):
            # Generate token signature
            payload = f"{uid}:{int(time.time())}"
            sig = sign(payload)
            
            # Create token in database
            await create_token(uid, payload, sig, expire_hours=12)
            
            # Generate ad URL
            encoded_payload = base64.urlsafe_b64encode(payload.encode()).decode()
            ad_url = f"{BASE_URL}/ad?payload={encoded_payload}&sig={sig}"
            
            # Shorten the ad URL (optional)
            try:
                short_url = short_adrinolinks(ad_url)
            except:
                short_url = ad_url
            
            # Send token verification message
            await message.reply_text(
                "⚠️ **Token Required!**

"
                "Your token has expired or is invalid.
"
                "Please watch the ad to generate a new token.

"
                "Token will be valid for **12 hours** after activation.

"
                f"🔗 **Click here:** {short_url}",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Generate Token", url=short_url)]
                ])
            )
            logger.info(f"Token required for user {uid}")
            return
        
        # ------------------------------
        # RETRIEVE AND SEND FILES
        # ------------------------------
        temp_msg = await message.reply("⏳ Please wait, fetching files...")
        
        try:
            messages = await get_messages(client, ids)
            logger.info(f"Retrieved {len(messages)} messages for user {uid}")
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            await temp_msg.delete()
            await message.reply_text("❌ Files not found! Link may be expired or invalid.")
            return
        
        await temp_msg.delete()
        
        # Counter for tracking
        sent_count = 0
        error_count = 0
        
        # Send each file
        for idx, msg in enumerate(messages):
            # Skip if message is None or empty
            if not msg:
                logger.warning(f"Skipping empty message at index {idx}")
                error_count += 1
                continue
            
            # ------------------------------
            # FIXED: Caption Logic for ALL Media Types
            # ------------------------------
            if CUSTOM_CAPTION:
                filename = "File"
                
                # Determine file type and name
                if msg.document:
                    filename = msg.document.file_name
                elif msg.photo:
                    filename = "Photo"
                elif msg.video:
                    filename = msg.video.file_name if msg.video.file_name else "Video"
                elif msg.audio:
                    filename = msg.audio.file_name if msg.audio.file_name else "Audio"
                elif msg.voice:
                    filename = "Voice Message"
                elif msg.sticker:
                    filename = "Sticker"
                elif msg.animation:
                    filename = "GIF Animation"
                
                caption = CUSTOM_CAPTION.format(
                    previouscaption="" if not msg.caption else msg.caption.html,
                    filename=filename
                )
            else:
                caption = "" if not msg.caption else msg.caption.html
            
            # Reply markup (buttons)
            reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None
            
            # Try to send the file
            try:
                copied = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    parse_mode="html",
                    reply_markup=reply_markup,
                    protect_content=PROTECT_CONTENT
                )
                
                sent_count += 1
                logger.info(f"Sent file {idx + 1} to user {uid}")
                
                # Auto-delete if enabled
                if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
                    asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                
                # Small delay to avoid flooding
                await asyncio.sleep(0.5)
                
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.x} seconds")
                await asyncio.sleep(e.x)
                
                # Retry after flood wait
                try:
                    copied = await msg.copy(
                        chat_id=uid,
                        caption=caption,
                        parse_mode="html",
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    
                    sent_count += 1
                    
                    if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                        
                except Exception as retry_error:
                    logger.error(f"Retry failed for message {idx}: {retry_error}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error copying message {idx}: {e}")
                error_count += 1
        
        # ------------------------------
        # SEND SUMMARY MESSAGE
        # ------------------------------
        if sent_count > 0:
            summary = f"✅ **Successfully sent {sent_count} file(s)**"
            
            if error_count > 0:
                summary += f"
⚠️ {error_count} file(s) failed to send"
            
            if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
                minutes = FILE_AUTO_DELETE // 60
                seconds = FILE_AUTO_DELETE % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                summary += f"

🗑️ Files will auto-delete in **{time_str}**"
            
            await message.reply_text(summary)
        else:
            await message.reply_text(
                "❌ Failed to send any files!

"
                "Possible reasons:
"
                "• Files may have been deleted from database
"
                "• Bot lacks permissions in DB channel
"
                "• Link has expired

"
                "Please contact admin if this persists."
            )
        
        logger.info(f"File delivery complete for user {uid}: {sent_count} sent, {error_count} failed")
        return
    
    # ------------------------------
    # WELCOME MESSAGE (No file link)
    # ------------------------------
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Channel", url="https://t.me/your_channel"),
            InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/your_dev")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            InlineKeyboardButton("📊 About", callback_data="about")
        ]
    ])
    
    await message.reply_text(
        text=START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )
    
    logger.info(f"Sent welcome message to user {uid}")

# ------------------------------
# USERS COMMAND (Admin Only)
# ------------------------------
@Bot.on_message(filters.command('users') & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    """Get total users count"""
    msg = await message.reply("⏳ Fetching user data...")
    users = await full_userbase()
    await msg.edit(f"👥 **Total Users:** `{len(users)}`")
    logger.info(f"Admin {message.from_user.id} checked user count: {len(users)}")

# ------------------------------
# BROADCAST COMMAND (Admin Only)
# ------------------------------
@Bot.on_message(filters.command('broadcast') & filters.user(ADMINS))
async def broadcast_handler(client: Bot, message: Message):
    """Broadcast message to all users"""
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("⏳ Broadcasting message...")
        
        for user_id in query:
            try:
                await broadcast_msg.copy(chat_id=user_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id=user_id)
                successful += 1
            except UserIsBlocked:
                await del_user(user_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(user_id)
                deleted += 1
            except:
                unsuccessful += 1
            
            total += 1
        
        status = f"✅ **Broadcast Completed!**

"
        status += f"Total Users: `{total}`
"
        status += f"Successful: `{successful}`
"
        status += f"Blocked: `{blocked}`
"
        status += f"Deleted Accounts: `{deleted}`
"
        status += f"Failed: `{unsuccessful}`"
        
        await pls_wait.edit(status)
        logger.info(f"Broadcast completed: {successful}/{total} successful")
    else:
        await message.reply_text("❌ Please reply to a message to broadcast!")

# ------------------------------
# GENLINK COMMAND (Admin Only)
# ------------------------------
@Bot.on_message(filters.command('genlink') & filters.user(ADMINS))
async def gen_link_handler(client: Bot, message: Message):
    """Generate shareable link from message ID"""
    replied = message.reply_to_message
    if not replied:
        return await message.reply_text("❌ Reply to a message in DB channel to generate link!")
    
    # Get message ID from DB channel
    msg_id = replied.forward_from_message_id if replied.forward_from_message_id else replied.id
    
    # Generate encoded link
    converted_id = msg_id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    
    await message.reply_text(
        f"✅ **Link Generated!**

"
        f"📎 **Link:** `{link}`

"
        f"📊 **Message ID:** `{msg_id}`",
        disable_web_page_preview=True,
        quote=True
    )
    logger.info(f"Admin {message.from_user.id} generated link for message {msg_id}")

# ------------------------------
# BATCH COMMAND (Admin Only)
# ------------------------------
@Bot.on_message(filters.command('batch') & filters.user(ADMINS))
async def batch_handler(client: Bot, message: Message):
    """Generate batch link for multiple files"""
    if ' ' in message.text:
        # Extract start and end message IDs
        try:
            _, *args = message.text.split(" ")
            if len(args) == 2:
                first_msg_id = int(args[0])
                last_msg_id = int(args[1])
            else:
                return await message.reply_text(
                    "❌ **Invalid format!**

"
                    "Usage: `/batch <first_msg_id> <last_msg_id>`
"
                    "Example: `/batch 100 150`"
                )
        except ValueError:
            return await message.reply_text("❌ Message IDs must be numbers!")
        
        # Validate IDs
        if first_msg_id > last_msg_id:
            return await message.reply_text("❌ First message ID must be less than last message ID!")
        
        # Generate batch link
        converted_first = first_msg_id * abs(client.db_channel.id)
        converted_last = last_msg_id * abs(client.db_channel.id)
        string = f"get-{converted_first}-{converted_last}"
        base64_string = await encode(string)
        link = f"https://t.me/{client.username}?start={base64_string}"
        
        await message.reply_text(
            f"✅ **Batch Link Generated!**

"
            f"📎 **Link:** `{link}`

"
            f"📊 **First Message:** `{first_msg_id}`
"
            f"📊 **Last Message:** `{last_msg_id}`
"
            f"📦 **Total Files:** `{last_msg_id - first_msg_id + 1}`",
            disable_web_page_preview=True,
            quote=True
        )
        logger.info(f"Admin {message.from_user.id} generated batch link: {first_msg_id}-{last_msg_id}")
    else:
        await message.reply_text(
            "❌ **Invalid format!**

"
            "Usage: `/batch <first_msg_id> <last_msg_id>`

"
            "Example: `/batch 100 150`
"
            "This will create a link for all messages from ID 100 to 150"
        )

# ------------------------------
# STATS COMMAND (Admin Only)
# ------------------------------
@Bot.on_message(filters.command('stats') & filters.user(ADMINS))
async def stats_handler(client: Bot, message: Message):
    """Show bot statistics"""
    users = await full_userbase()
    total_users = len(users)
    
    uptime = (time.time() - client.start_time) if hasattr(client, 'start_time') else 0
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    stats_text = f"📊 **Bot Statistics**

"
    stats_text += f"👥 Total Users: `{total_users}`
"
    stats_text += f"⏰ Uptime: `{hours}h {minutes}m`
"
    stats_text += f"🤖 Bot: @{client.username}"
    
    await message.reply_text(stats_text)
    logger.info(f"Admin {message.from_user.id} checked stats")
