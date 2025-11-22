# File Sharing Bot - Single File Implementation
# Based on JishuDeveloper's File-Sharing-Bot Architecture
# All modules combined into one bot.py file

import os
import sys
import asyncio
import datetime
import time
import string
import base64
import logging
from typing import Union, Optional, AsyncGenerator
from aiohttp import web

# Pyrogram
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant
from pyrogram.errors.exceptions.bad_request_400 import MessageEmpty, PeerIdInvalid

# Database 
from motor.motor_asyncio import AsyncIOMotorClient

# Logging setup
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# ===========================================
# Configuration
# ===========================================

class Config(object):
    # Mandatory
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
    OWNER_ID = int(os.environ.get("OWNER_ID", 0))
    DB_URL = os.environ.get("DB_URL", "")
    DB_NAME = os.environ.get("DB_NAME", "filesharexbot")
    
    # Optional - Port for health check
    PORT = int(os.environ.get("PORT", 10000))
    
    # Optional - Admin List
    ADMINS = []
    ADMINS.append(OWNER_ID)
    if os.environ.get("ADMINS"):
        ADMINS.extend([int(x) for x in os.environ.get("ADMINS", "0").split()])
    
    # Optional - Force Subscribe
    FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "0")
    if FORCE_SUB_CHANNEL == "0":
        FORCE_SUB_CHANNEL = None
    else:
        try:
            FORCE_SUB_CHANNEL = int(FORCE_SUB_CHANNEL)
        except:
            FORCE_SUB_CHANNEL = FORCE_SUB_CHANNEL
    
    # Optional - Features
    PROTECT_CONTENT = True if os.environ.get("PROTECT_CONTENT", "False") == "True" else False
    FILE_AUTO_DELETE = int(os.environ.get("FILE_AUTO_DELETE", 600))  # in seconds
    DISABLE_CHANNEL_BUTTON = True if os.environ.get("DISABLE_CHANNEL_BUTTON", "False") == "True" else False
    
    # Optional - Custom Messages
    START_MESSAGE = os.environ.get("START_MESSAGE", """
Hello {first}

I can store private files in Specified Channel and other users can access it from special link.
""")
    
    FORCE_SUB_MESSAGE = os.environ.get("FORCE_SUB_MESSAGE", """
Hello {first}

<b>You need to join in my Channel/Group to use me

Kindly Please join Channel</b>
""")
    
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)
    
    BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"
    
    USER_REPLY_TEXT = "âŒDon't send me messages directly I'm only File Share bot!"


# ===========================================
# Database Functions
# ===========================================

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
    
    def new_user(self, id, name):
        return dict(
            id=id,
            name=name,
            ban_status=dict(
                is_banned=False,
                ban_reason="",
            ),
        )
    
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
    
    async def remove_ban(self, id):
        ban_status = dict(
            is_banned=False,
            ban_reason='',
        )
        await self.col.update_one({'id': id}, {'$set': {'ban_status': ban_status}})
    
    async def ban_user(self, user_id, ban_reason="No Reason"):
        ban_status = dict(
            is_banned=True,
            ban_reason=ban_reason,
        )
        await self.col.update_one({'id': user_id}, {'$set': {'ban_status': ban_status}})
    
    async def get_ban_status(self, id):
        default = dict(
            is_banned=False,
            ban_reason='',
        )
        user = await self.col.find_one({'id': int(id)})
        return user.get('ban_status', default)
    
    async def get_all_banned_users(self):
        return self.col.find({'ban_status.is_banned': True})


# ===========================================
# Helper Functions
# ===========================================

def get_readable_time(seconds: int) -> str:
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    
    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "
    
    time_list.reverse()
    ping_time += ":".join(time_list)
    
    return ping_time


def get_file_id(msg: Message):
    if msg.media:
        for message_type in ("photo", "animation", "audio", "document", "video", "video_note", "voice", "sticker"):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj


async def forward_to_channel(message: Message, client: Client, batch_id: int):
    try:
        msg = await message.forward(Config.CHANNEL_ID)
        return msg.id
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await forward_to_channel(message, client, batch_id)


def encode(file_id: str) -> str:
    string_bytes = file_id.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return base64_bytes.decode("ascii").rstrip("=")


def decode(base64_string: str) -> str:
    base64_string = base64_string.strip()
    # Add padding
    padding = 4 - len(base64_string) % 4
    if padding != 4:
        base64_string += "=" * padding
    
    string_bytes = base64.urlsafe_b64decode(base64_string)
    return string_bytes.decode("ascii")


async def get_messages(client: Client, message_ids: list):
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temp_messages = message_ids[total_messages:total_messages + 200]
        try:
            msgs = await client.get_messages(
                chat_id=Config.CHANNEL_ID,
                message_ids=temp_messages
            )
            total_messages += len(temp_messages)
            messages.extend(msgs)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except:
            pass
    return messages


# ===========================================
# Health Check Server for Render
# ===========================================

async def health_check(request):
    return web.Response(text="âœ… Bot is running!", status=200)


async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    LOGGER.info(f"Health check server started on port {Config.PORT}")


# ===========================================
# Bot Client & Database
# ===========================================

Bot = Client(
    name="Bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=50,
    sleep_threshold=10,
)

db = Database(Config.DB_URL, Config.DB_NAME)

START_TIME = time.time()


# ===========================================
# Check Force Subscribe
# ===========================================

async def is_subscribed(client: Client, query: CallbackQuery):
    if Config.FORCE_SUB_CHANNEL:
        try:
            user = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, query.from_user.id)
        except UserNotParticipant:
            return False
        except Exception:
            return True
        else:
            if user.status != "kicked":
                return True
            else:
                return False
    return True


# ===========================================
# Start Command Handler
# ===========================================

@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    id = message.from_user.id
    user_name = '@' + message.from_user.username if message.from_user.username else None
    
    try:
        await message.react("ðŸ”¥")
    except:
        pass
    
    if not await db.is_user_exist(id):
        await db.add_user(id, user_name)
    
    if Config.FORCE_SUB_CHANNEL:
        try:
            user = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, id)
            if user.status == "kicked":
                await message.reply_text("You are banned!")
                return
        except UserNotParticipant:
            try:
                invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
            except Exception as err:
                LOGGER.exception(err)
                await message.reply_text(
                    "Something went wrong. Contact my owner.",
                    disable_web_page_preview=True
                )
                return
            
            await message.reply_text(
                Config.FORCE_SUB_MESSAGE.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name or "",
                    username=message.from_user.username or "None",
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("ðŸ”” Join Channel", url=invite_link.invite_link)],
                    [InlineKeyboardButton("â™»ï¸ Refresh", callback_data=f"refreshmeh_{message.id}")]
                ]),
                disable_web_page_preview=True
            )
            return
        except Exception as err:
            LOGGER.exception(err)
    
    text = message.text
    if len(text) > 7:
        try:
            base64_string = text.split(" ", 1)[1]
        except:
            return
        
        string = await decode(base64_string)
        argument = string.split("-")
        
        if len(argument) == 3:
            # Batch files
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except:
                return
            
            if start <= end:
                ids = range(start, end + 1)
            else:
                ids = []
                i = start
                while True:
                    ids.append(i)
                    i -= 1
                    if i < end:
                        break
        
        elif len(argument) == 2:
            # Single file
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except:
                return
        
        temp_msg = await message.reply("Please wait...")
        
        try:
            messages = await get_messages(client, ids)
        except:
            await message.reply_text("Something went wrong..!")
            return
        
        await temp_msg.delete()
        
        for msg in messages:
            caption = Config.CUSTOM_CAPTION.format(
                filename=msg.document.file_name,
                previouscaption=msg.caption.html if msg.caption else "",
                filesize=msg.document.file_size
            ) if Config.CUSTOM_CAPTION and msg.document else (msg.caption.html if msg.caption else "")
            
            reply_markup = msg.reply_markup if not Config.DISABLE_CHANNEL_BUTTON else None
            
            try:
                copied_msg = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    reply_markup=reply_markup,
                    protect_content=Config.PROTECT_CONTENT
                )
                
                if Config.FILE_AUTO_DELETE > 0:
                    asyncio.create_task(delete_after_delay(copied_msg, Config.FILE_AUTO_DELETE))
                
            except FloodWait as e:
                await asyncio.sleep(e.value)
                copied_msg = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    reply_markup=reply_markup,
                    protect_content=Config.PROTECT_CONTENT
                )
                
                if Config.FILE_AUTO_DELETE > 0:
                    asyncio.create_task(delete_after_delay(copied_msg, Config.FILE_AUTO_DELETE))
            except Exception as e:
                LOGGER.exception(e)
                continue
            
            await asyncio.sleep(1)
        return
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ”° About", callback_data="about"),
         InlineKeyboardButton("ðŸ” Close", callback_data="close")]
    ])
    
    await message.reply_text(
        text=Config.START_MESSAGE.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=message.from_user.username or "None",
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )


async def delete_after_delay(message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# ===========================================
# Callback Query Handler
# ===========================================

@Bot.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    
    if data == "about":
        await query.message.edit_text(
            text="<b>â—‹ Creator : <a href='https://t.me/JishuDeveloper'>Jishu Developer</a>\nâ—‹ Language : <code>Python3</code>\nâ—‹ Library : <a href='https://docs.pyrogram.org/'>Pyrogram asyncio</a>\nâ—‹ Source Code : <a href='https://github.com/JishuDeveloper/File-Sharing-Bot'>Click here</a>\nâ—‹ Channel : @JishuBotz\nâ—‹ Support Group : @JishuDeveloper</b>",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ðŸ”’ Close", callback_data="close")]
            ])
        )
    
    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
    
    elif data.startswith("refreshmeh_"):
        if Config.FORCE_SUB_CHANNEL:
            if await is_subscribed(client, query):
                await query.answer("You're subscribed now âœ…", show_alert=True)
                await query.message.delete()
                await start_command(client, query.message.reply_to_message)
            else:
                await query.answer("You didn't join the channel âŒ", show_alert=True)


# ===========================================
# Channel Posts Handler (Save Files)
# ===========================================

@Bot.on_message(filters.channel & filters.incoming & filters.chat(Config.CHANNEL_ID))
async def channel_post(client: Client, message: Message):
    LOGGER.info(f"New post in channel: {message.id}")


# ===========================================
# Admin Commands
# ===========================================

@Bot.on_message(filters.command('users') & filters.private & filters.user(Config.ADMINS))
async def get_users(client: Client, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text="Processing...")
    users = await db.total_users_count()
    await msg.edit(f"{users} users are using this bot")


@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(Config.ADMINS))
async def send_text(client: Client, message: Message):
    if message.reply_to_message:
        query = await db.total_users_count()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<code>Broadcasting Message.. This will Take Some Time</code>")
        async for user in db.get_all_users():
            try:
                await broadcast_msg.copy(user['id'])
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await broadcast_msg.copy(user['id'])
                successful += 1
            except UserIsBlocked:
                blocked += 1
            except InputUserDeactivated:
                deleted += 1
            except:
                unsuccessful += 1
            
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{query}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)
    
    else:
        msg = await message.reply("Please Reply to a Message!")
        await asyncio.sleep(8)
        await msg.delete()


@Bot.on_message(filters.command('stats') & filters.user(Config.ADMINS))
async def stats(client: Client, message: Message):
    uptime = get_readable_time((time.time() - START_TIME))
    await message.reply(Config.BOT_STATS_TEXT.format(uptime=uptime))


@Bot.on_message(filters.command('batch') & filters.private & filters.user(Config.ADMINS))
async def batch(client: Client, message: Message):
    while True:
        try:
            first_message = await client.ask(text="Forward the First Message from DB Channel (with Quotes)..\n\nor Send the DB Channel Post Link", chat_id=message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        
        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("âŒ Error\n\nThis Forwarded Post is not from my DB Channel or this Link is not taken from DB Channel", quote=True)
            continue
    
    while True:
        try:
            second_message = await client.ask(text="Forward the Last Message from DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id=message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        
        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("âŒ Error\n\nThis Forwarded Post is not from my DB Channel or this Link is not taken from DB Channel", quote=True)
            continue
    
    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ” Share URL", url=f'https://telegram.me/share/url?url={link}')]])
    await second_message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)


@Bot.on_message(filters.command('genlink') & filters.private & filters.user(Config.ADMINS))
async def link_generator(client: Client, message: Message):
    while True:
        try:
            channel_message = await client.ask(text="Forward Message from the DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id=message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("âŒ Error\n\nThis Forwarded Post is not from my DB Channel or this Link is not taken from DB Channel", quote=True)
            continue
    
    base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
    link = f"https://t.me/{client.username}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ” Share URL", url=f'https://telegram.me/share/url?url={link}')]])
    await channel_message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)


async def get_message_id(client: Client, message: Message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == Config.CHANNEL_ID:
            return message.forward_from_message_id
        else:
            return 0
    elif message.forward_sender_name:
        return 0
    elif message.text:
        pattern = "https://t.me/(?:c/)?(.*)/(\d+)"
        matches = re.match(pattern, message.text)
        if not matches:
            return 0
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        if channel_id.isdigit():
            if f"-100{channel_id}" == str(Config.CHANNEL_ID):
                return msg_id
        elif channel_id == client.db_channel.username:
            return msg_id
    else:
        return 0


# ===========================================
# Other Messages Handler
# ===========================================

@Bot.on_message(filters.private & filters.incoming)
async def not_valid(client: Client, message: Message):
    await message.reply_text(Config.USER_REPLY_TEXT, quote=True)


# ===========================================
# Main Function
# ===========================================

async def main():
    # Set db_channel attribute
    Bot.db_channel = await Bot.get_chat(Config.CHANNEL_ID)
    
    # Start health check server
    await start_health_server()
    
    # Start bot
    await Bot.start()
    LOGGER.info("Bot Started!")
    
    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    import re
    
    # Validation
    if not Config.BOT_TOKEN:
        LOGGER.error("BOT_TOKEN not found!")
        sys.exit(1)
    
    if not Config.API_HASH or Config.API_ID == 0:
        LOGGER.error("API_HASH or API_ID not found!")
        sys.exit(1)
    
    if Config.CHANNEL_ID == 0:
        LOGGER.error("CHANNEL_ID not found!")
        sys.exit(1)
    
    if not Config.DB_URL:
        LOGGER.error("DB_URL not found!")
        sys.exit(1)
    
    # Run bot
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot Stopped!")
