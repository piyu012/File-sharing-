import os, time, hmac, hashlib, asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS, START_MSG, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL
from helper_func import encode, decode, get_messages, is_subscribed, short_url
from db_init import has_pass, grant_pass, use_token, present_user, add_user, full_userbase, del_user
from pyrogram.errors import FloodWait

def sign(payload: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

async def delete_file_later(client, message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

@Bot.on_message(filters.command('start') & filters.private & is_subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id
    
    if not await present_user(uid):
        await add_user(uid)
    
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            string = await decode(base64_string)
            argument = string.split("-")
            
            if len(argument) == 3:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
                ids = range(start, end+1)
            elif len(argument) == 2:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            
            if not await has_pass(uid):
                payload = f"{uid}:{int(time.time())}"
                sig = sign(payload)
                watch_url = f"{BASE_URL}/watch?payload={payload}&sig={sig}"
                short_link = short_url(watch_url)
                
                await message.reply_text(
                    f"""Access Locked! Watch ad: {short_link}
Or use: /redeem TOKEN""",
                    disable_web_page_preview=True
                )
                return
            
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
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("About", callback_data="about")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ])
    
    first = message.from_user.first_name
    last = message.from_user.last_name if message.from_user.last_name else ""
    username = "@" + message.from_user.username if message.from_user.username else "None"
    
    text = START_MSG.format(first=first, last=last, username=username, mention=message.from_user.mention, id=message.from_user.id)
    
    await message.reply_text(text=text, reply_markup=reply_markup, disable_web_page_preview=True, quote=True)

@Bot.on_message(filters.command("redeem") & filters.private)
async def redeem_token(client: Bot, message: Message):
    uid = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 2:
        return await message.reply_text("Format: /redeem TOKEN")
    
    token = parts[1]
    hours = await use_token(token, uid)
    
    if hours is None:
        return await message.reply_text("Invalid, expired, or already used token!")
    
    await grant_pass(uid, hours)
    await message.reply_text(f"Token redeemed! Access for {hours} hours.")

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
                await msg.edit(f"Broadcasting... Total: {total}, Success: {success}, Blocked: {blocked}, Deleted: {deleted}, Failed: {failed}")
        
        await msg.edit(f"Broadcast Done! Total: {total}, Success: {success}, Blocked: {blocked}, Deleted: {deleted}, Failed: {failed}")
    else:
        await message.reply("Reply to a message to broadcast.")
