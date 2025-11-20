import os
import time
import hmac
import hashlib
import asyncio
import base64

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import ADMINS, START_MSG, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL
from helper_func import encode, decode, get_messages
from db_init import has_valid_token, create_token, present_user, add_user, full_userbase, del_user

def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()

def short_adrinolinks(long_url: str) -> str:
    from config import ADRINO_API
    import requests
    if not ADRINO_API:
        return long_url
    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}").json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

async def delete_file_later(client, message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id
    
    # Add user to database
    if not await present_user(uid):
        await add_user(uid)
    
    # Check if accessing file link
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            
            # Skip token check for "verified" parameter
            if base64_string == "verified":
                await message.reply_text("✅ Token verified successfully! You can now access files.")
                return
            
            string = await decode(base64_string)
            argument = string.split("-")
            
            if len(argument) == 3:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
                ids = range(start, end + 1)
            elif len(argument) == 2:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            else:
                ids = []

            # ===== TOKEN CHECK (NEW) =====
            if not await has_valid_token(uid):
                # Generate new token
                ts = int(time.time())
                payload = f"{uid}:{ts}"
                sig = sign(payload)
                
                await create_token(uid, payload, sig)
                
                encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
                url = f"{BASE_URL}/watch?data={encoded}"
                short_url = short_adrinolinks(url)
                
                await message.reply_text(
                    f"🔒 Access Locked!

"
                    f"Watch ad to unlock: {short_url}

"
                    f"Token valid for 12 hours after verification.",
                    disable_web_page_preview=True
                )
                return
            
            # User has valid token - send files
            temp_msg = await message.reply("Please wait...")
            
            try:
                messages = await get_messages(client, ids)
            except:
                await message.reply_text("Something went wrong!")
                return
            
            await temp_msg.delete()
            
            for msg in messages:
                try:
                    copied = await msg.copy(chat_id=message.from_user.id)
                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    copied = await msg.copy(chat_id=message.from_user.id)
                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                except:
                    pass
            return
        except:
            pass

    # Normal start message
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("About", callback_data="about")],
            [InlineKeyboardButton("Close", callback_data="close")]
        ]
    )

    first = message.from_user.first_name
    last = message.from_user.last_name if message.from_user.last_name else ""
    username = "@" + message.from_user.username if message.from_user.username else "None"

    text = START_MSG.format(
        first=first,
        last=last,
        username=username,
        mention=message.from_user.mention,
        id=message.from_user.id
    )

    await message.reply_text(
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )

@Bot.on_message(filters.command('users') & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    msg = await message.reply("Processing...")
    users = await full_userbase()
    await msg.edit(f"Total Users: {len(users)}")

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
                err = str(e).lower()
                if "blocked" in err:
                    blocked += 1
                    await del_user(user_id)
                elif "deleted" in err:
                    deleted += 1
                    await del_user(user_id)
                else:
                    failed += 1
            
            if (success + blocked + deleted + failed) % 20 == 0:
                await msg.edit(
                    f"Broadcasting...
Total: {total}
Success: {success}
"
                    f"Blocked: {blocked}
Deleted: {deleted}
Failed: {failed}"
                )
        
        await msg.edit(
            f"Broadcast Done!
Total: {total}
Success: {success}
"
            f"Blocked: {blocked}
Deleted: {deleted}
Failed: {failed}"
        )
    else:
        await message.reply("Reply to a message to broadcast.")
