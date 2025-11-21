import os
import time
import hmac
import hashlib
import asyncio
import base64
import logging
import requests

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import (
    ADMINS, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL, ADRINO_API
)
from helper_func import subscribed, encode, decode, get_messages
from db_init import add_user, del_user, full_userbase, present_user, has_valid_token, create_token


# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================================================
# HMAC SIGN FUNCTION
# =====================================================
def sign(data: str) -> str:
    """Generate HMAC signature for token verification"""
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


# =====================================================
# SHORT LINK FUNCTION (ADRINOLINKS) - FIXED
# =====================================================
def short_adrinolinks(long_url: str) -> str:
    """Shorten URL using Adrinolinks API with proper error handling"""
    
    # If no API key configured, return original URL
    if not ADRINO_API or ADRINO_API == "None":
        logger.info("No Adrinolinks API configured, using original URL")
        return long_url

    try:
        response = requests.get(
            "https://adrinolinks.com/api",
            params={"api": ADRINO_API, "url": long_url},
            timeout=10
        )
        
        logger.info(f"Adrinolinks response status: {response.status_code}")
        
        if response.status_code == 200:
            # Try to parse JSON
            try:
                data = response.json()
                if data.get("status") == "success":
                    short_url = data.get("shortenedUrl", long_url)
                    logger.info(f"URL shortened successfully: {short_url}")
                    return short_url
                else:
                    logger.warning(f"Adrinolinks returned error: {data}")
                    return long_url
            except requests.exceptions.JSONDecodeError as json_err:
                logger.error(f"JSON decode error: {json_err}")
                logger.error(f"Response text: {response.text[:500]}")
                return long_url
        else:
            logger.warning(f"Adrinolinks returned status {response.status_code}")
            return long_url
            
    except requests.exceptions.Timeout:
        logger.error("Adrinolinks API timeout")
        return long_url
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Adrinolinks request error: {req_err}")
        return long_url
    except Exception as e:
        logger.error(f"Unexpected shortener error: {e}")
        return long_url


# =====================================================
# AUTO DELETE FUNCTION
# =====================================================
async def delete_file_later(client: Bot, message: Message, delay: int):
    """Delete message after specified delay"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        logger.info(f"Auto-deleted message {message.id}")
    except Exception as e:
        logger.error(f"Failed to auto-delete: {e}")


# =====================================================
# /START COMMAND HANDLER
# =====================================================
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    """Main start command handler with file sharing and token verification"""
    
    uid = message.from_user.id
    logger.info(f"Start command from user {uid}")

    # ADD USER TO DATABASE
    if not await present_user(uid):
        try:
            await add_user(uid)
            logger.info(f"New user added: {uid}")
        except Exception as e:
            logger.error(f"Failed to add user: {e}")

    # ========== FILE LINK HANDLING ==========
    if len(message.text.split()) > 1:

        # Extract encoded string
        try:
            encoded = message.text.split(" ", 1)[1]
            logger.info(f"Processing link for user {uid}: {encoded[:20]}...")
        except:
            return await message.reply("❌ Invalid link format!")

        # Decode the link
        try:
            decoded = await decode(encoded)
            logger.info(f"Decoded: {decoded}")
            parts = decoded.split("-")
        except Exception as e:
            logger.error(f"Decode error: {e}")
            return await message.reply("❌ Corrupted or invalid link!")

        # Handle batch links (multiple files)
        if len(parts) == 3:
            try:
                start_id = int(parts[1])
                end_id = int(parts[2])
                logger.info(f"Batch request: {start_id} to {end_id}")
            except ValueError:
                return await message.reply("❌ Invalid batch link!")

            # Generate ID list
            if start_id <= end_id:
                ids = list(range(start_id, end_id + 1))
            else:
                # Reverse order
                ids = list(range(end_id, start_id + 1))

        # Handle single file link
        elif len(parts) == 2:
            try:
                file_id = int(parts[1])
                ids = [file_id]
                logger.info(f"Single file request: {file_id}")
            except ValueError:
                return await message.reply("❌ Invalid file link!")

        else:
            return await message.reply("❌ Invalid link format!")

        # ========== TOKEN VERIFICATION ==========
        if not await has_valid_token(uid):
            logger.info(f"Token required for user {uid}")
            
            # Generate token data
            payload = f"{uid}:{int(time.time())}"
            sig = sign(payload)

            # Create token in database
            try:
                await create_token(uid, payload, sig, expire_hours=12)
                logger.info(f"Token created for user {uid}")
            except Exception as e:
                logger.error(f"Token creation error: {e}")

            # Generate ad verification URL
            encoded_payload = base64.urlsafe_b64encode(payload.encode()).decode()
            token_url = f"{BASE_URL}/ad?payload={encoded_payload}&sig={sig}"
            
            logger.info(f"Token URL: {token_url}")

            # Try to shorten the URL
            try:
                short_url = short_adrinolinks(token_url)
            except Exception as e:
                logger.error(f"Shortener failed: {e}")
                short_url = token_url

            # Send token required message
            return await message.reply(
                "⚠️ **Token Required!**

"
                "Your token has expired or is invalid.
"
                "Please verify by watching the ad.

"
                "Token will be valid for **12 hours** after activation.

"
                f"🔗 **Click here:** {short_url}",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Generate Token", url=short_url)]
                ])
            )

        # ========== FETCH FILES FROM DB CHANNEL ==========
        wait_msg = await message.reply("⏳ Fetching files...")

        try:
            msgs = await get_messages(client, ids)
            logger.info(f"Retrieved {len(msgs)} messages")
        except Exception as e:
            logger.error(f"Get messages error: {e}")
            await wait_msg.delete()
            return await message.reply(
                "❌ **File not found!**

"
                "Possible reasons:
"
                "• File may have been deleted
"
                "• Link has expired
"
                "• Bot lacks DB channel permissions"
            )

        await wait_msg.delete()

        # Counters
        sent = 0
        failed = 0

        # Send each file
        for idx, msg in enumerate(msgs):

            if not msg:
                logger.warning(f"Skipping None message at index {idx}")
                failed += 1
                continue

            # ========== CAPTION HANDLING (FIXED FOR ALL MEDIA TYPES) ==========
            if CUSTOM_CAPTION:
                filename = "File"

                if msg.document:
                    filename = msg.document.file_name
                elif msg.video:
                    filename = msg.video.file_name if msg.video.file_name else "Video"
                elif msg.audio:
                    filename = msg.audio.file_name if msg.audio.file_name else "Audio"
                elif msg.photo:
                    filename = "Photo"
                elif msg.voice:
                    filename = "Voice Message"
                elif msg.sticker:
                    filename = "Sticker"
                elif msg.animation:
                    filename = "GIF"

                caption = CUSTOM_CAPTION.format(
                    previouscaption=msg.caption.html if msg.caption else "",
                    filename=filename
                )
            else:
                caption = msg.caption.html if msg.caption else ""

            # Reply markup (buttons)
            reply_markup = None if DISABLE_CHANNEL_BUTTON else msg.reply_markup

            # Try to send the file
            try:
                copied = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="html",
                    protect_content=PROTECT_CONTENT
                )

                sent += 1
                logger.info(f"Sent file {idx + 1}/{len(msgs)} to user {uid}")

                # Auto-delete if enabled
                if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
                    asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))

                # Small delay to avoid flood
                await asyncio.sleep(0.5)

            except FloodWait as e:
                logger.warning(f"FloodWait: {e.value}s")
                await asyncio.sleep(e.value)
                # Retry once after flood wait
                try:
                    copied = await msg.copy(
                        chat_id=uid,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="html",
                        protect_content=PROTECT_CONTENT
                    )
                    sent += 1
                    if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                except Exception as retry_err:
                    logger.error(f"Retry failed: {retry_err}")
                    failed += 1

            except Exception as e:
                logger.error(f"Copy error for message {idx}: {e}")
                failed += 1

        # ========== SEND SUMMARY ==========
        summary = f"✅ **Sent: {sent}**"
        
        if failed > 0:
            summary += f"
⚠️ **Failed: {failed}**"

        if FILE_AUTO_DELETE and FILE_AUTO_DELETE > 0:
            mins = FILE_AUTO_DELETE // 60
            secs = FILE_AUTO_DELETE % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            summary += f"
🗑️ **Auto-delete in:** {time_str}"

        logger.info(f"Delivery complete for user {uid}: {sent} sent, {failed} failed")
        
        return await message.reply(summary)

    # ========== NORMAL START MESSAGE (NO FILE LINK) ==========
    btn = InlineKeyboardMarkup([
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
        START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=f"@{message.from_user.username}" if message.from_user.username else "No Username",
            mention=message.from_user.mention,
            id=uid
        ),
        reply_markup=btn,
        disable_web_page_preview=True
    )


# =====================================================
# ADMIN COMMANDS
# =====================================================

@Bot.on_message(filters.command("users") & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    """Get total user count"""
    users = await full_userbase()
    await message.reply(f"👥 **Total Users:** `{len(users)}`")
    logger.info(f"Admin {message.from_user.id} checked user count")


@Bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client: Bot, message: Message):
    """Show bot statistics"""
    users = await full_userbase()
    
    uptime = time.time() - getattr(client, "start_time", time.time())
    h = int(uptime // 3600)
    m = int((uptime % 3600) // 60)

    await message.reply(
        f"📊 **Bot Statistics**

"
        f"👥 Total Users: `{len(users)}`
"
        f"⏰ Uptime: `{h}h {m}m`
"
        f"🤖 Bot: @{client.username}"
    )
    logger.info(f"Admin {message.from_user.id} checked stats")


@Bot.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client: Bot, message: Message):
    """Broadcast message to all users"""
    
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a message to broadcast!")
    
    users = await full_userbase()
    broadcast_msg = message.reply_to_message
    
    success = 0
    failed = 0
    
    status_msg = await message.reply("⏳ Broadcasting...")
    
    for user_id in users:
        try:
            await broadcast_msg.copy(chat_id=user_id)
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except:
            failed += 1
    
    await status_msg.edit(
        f"✅ **Broadcast Complete!**

"
        f"📤 Sent: `{success}`
"
        f"❌ Failed: `{failed}`"
    )
    
    logger.info(f"Broadcast: {success} success, {failed} failed")
