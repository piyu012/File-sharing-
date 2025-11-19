import os, time, hmac, hashlib, asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL
from helper_func import encode, decode, get_messages, is_subscribed, short_url
from db_init import has_pass, grant_pass, mint_token, use_token, present_user, add_user, full_userbase, del_user
from database import database as db

# ========== HMAC SIGNATURE ==========
def sign(payload: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

# ========== START COMMAND ==========
@Bot.on_message(filters.command('start') & filters.private & is_subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id
    
    # Add user to database if not present
    if not await present_user(uid):
        await add_user(uid)
    
    # Check if accessing file
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            string = await decode(base64_string)
            argument = string.split("-")
            
            if len(argument) == 3:
                # Batch file access
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
                ids = range(start, end+1)
            elif len(argument) == 2:
                # Single file access
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            
            # Check if user has active pass
            if not await has_pass(uid):
                # Generate token with ad link
                payload = f"{uid}:{int(time.time())}"
                sig = sign(payload)
                watch_url = f"{BASE_URL}/watch?payload={payload}&sig={sig}"
                short_link = short_url(watch_url)
                
                await message.reply_text(
                    f"🔒 Access Locked!

"
                    f"Watch ad to unlock: {short_link}

"
                    f"या token है तो /redeem TOKEN भेजें।",
                    disable_web_page_preview=True
                )
                return
            
            # User has pass - send files
            temp_msg = await message.reply("Please wait...")
            
            try:
                messages = await get_messages(client, ids)
            except:
                await message.reply_text("Something Went Wrong..!")
                return
            
            await temp_msg.delete()
            
            for msg in messages:
                caption = CUSTOM_CAPTION.format(previouscaption="" if not msg.caption else msg.caption.html, filename=msg.document.file_name) if CUSTOM_CAPTION and msg.document else ("" if not msg.caption else msg.caption.html)
                
                reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None
                
                try:
                    copied_msg = await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode='html',
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    
                    # Auto delete
                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file(client, copied_msg, FILE_AUTO_DELETE))
                        
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    copied_msg = await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode='html',
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file(client, copied_msg, FILE_AUTO_DELETE))
                except:
                    pass
            return
        except:
            pass
    
    # Normal start message
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("😊 About Me", callback_data="about")],
            [InlineKeyboardButton("🔒 Close", callback_data="close")]
        ]
    )
    
    await message.reply_text(
        text=START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )

# ========== AUTO DELETE ==========
async def delete_file(client, message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

# ========== REDEEM TOKEN ==========
@Bot.on_message(filters.command("redeem") & filters.private)
async def redeem_token(client: Bot, message: Message):
    uid = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 2:
        return await message.reply_text("❌ Format: /redeem TOKEN")
    
    token = parts[1]
    hours = await use_token(token, uid)
    
    if hours is None:
        return await message.reply_text("❌ Invalid, expired, or already used token!")
    
    await grant_pass(uid, hours)
    await message.reply_text(f"✅ Token redeemed! Access granted for {hours} hours.")

# ========== USERS COUNT (ADMIN) ==========
@Bot.on_message(filters.command('users') & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    msg = await message.reply("Processing...")
    users = await full_userbase()
    await msg.edit(f"📊 Total Users: {len(users)}")

# ========== BROADCAST (ADMIN) ==========
@Bot.on_message(filters.command('broadcast') & filters.user(ADMINS))
async def broadcast(client: Bot, message: Message):
    if message.reply_to_message:
        msg = await message.reply("Broadcasting...")
        users = await full_userbase()
        
        total = len(users)
        success = 0
        blocked = 0
        deleted = 0
        failed = 0
        
        for user_id in users:
            try:
                await message.reply_to_message.copy(user_id)
                success += 1
            except Exception as e:
                if "blocked" in str(e).lower():
                    blocked += 1
                    await del_user(user_id)
                elif "deleted" in str(e).lower():
                    deleted += 1
                    await del_user(user_id)
                else:
                    failed += 1
            
            if (success + blocked + deleted + failed) % 20 == 0:
                await msg.edit(
                    f"Broadcasting...

"
                    f"Total: {total}
"
                    f"Success: {success}
"
                    f"Blocked: {blocked}
"
                    f"Deleted: {deleted}
"
                    f"Failed: {failed}"
                )
        
        await msg.edit(
            f"✅ Broadcast Complete!

"
            f"Total: {total}
"
            f"Success: {success}
"
            f"Blocked: {blocked}
"
            f"Deleted: {deleted}
"
            f"Failed: {failed}"
        )
    else:
        await message.reply("Reply to a message to broadcast.")
