import os
import sys
import time
import asyncio
import datetime
import logging
import traceback
from typing import Union

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant, PeerIdInvalid, ChannelInvalid
from pyrogram.errors.exceptions.bad_request_400 import MessageEmpty

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from aiohttp import web
import base64

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    ADMINS = [OWNER_ID]
    admin_list = os.environ.get("ADMINS", "")
    if admin_list:
        ADMINS.extend([int(x) for x in admin_list.split()])
    
    FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "0")
    if FORCE_SUB_CHANNEL != "0":
        try:
            FORCE_SUB_CHANNEL = int(FORCE_SUB_CHANNEL)
        except:
            FORCE_SUB_CHANNEL = str(FORCE_SUB_CHANNEL)
    
    START_MESSAGE = os.environ.get("START_MESSAGE", 
        "<b>ðŸ‘‹ Hello {mention}!\n\n"
        "I'm a File Sharing Bot.\n\n"
        "You can store files and share them using special links!</b>"
    )
    
    FORCE_SUB_MESSAGE = os.environ.get("FORCE_SUB_MESSAGE",
        "<b>âš ï¸ Join our channel first!\n\n"
        "Please join @{channel} to use this bot.\n\n"
        "After joining, click on /start again.</b>"
    )
    
    CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "")
    DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False").lower() == "true"
    BOT_STATS_TEXT = os.environ.get("BOT_STATS_TEXT",
        "<b>ðŸ“Š Bot Statistics\n\n"
        "â± Bot Uptime: {uptime}\n"
        "ðŸ‘¥ Total Users: {users}\n"
        "ðŸ“ Total Files: {files}</b>"
    )
    USER_REPLY_TEXT = os.environ.get("USER_REPLY_TEXT",
        "<b>âŒ Invalid command!\n\nUse /start to start the bot.</b>"
    )

async def health_check(request):
    return web.Response(text="Bot is running! âœ…", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Health check server started on port {Config.PORT}")

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db['users']
        self.files = self.db['file_ids']

    async def add_user(self, user_id, first_name, username):
        try:
            user_data = {
                'id': user_id,
                'first_name': first_name,
                'username': username,
                'join_date': datetime.datetime.now()
            }
            await self.users.update_one(
                {'id': user_id},
                {'$set': user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    async def get_user(self, user_id):
        return await self.users.find_one({'id': user_id})

    async def get_all_users(self):
        return await self.users.find().to_list(length=None)

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def add_file(self, file_id, unique_id, caption=None):
        try:
            file_data = {
                'file_id': file_id,
                'unique_id': unique_id,
                'caption': caption
            }
            await self.files.insert_one(file_data)
            return True
        except Exception as e:
            logger.error(f"Error adding file: {e}")
            return False

    async def get_file(self, unique_id):
        return await self.files.find_one({'unique_id': unique_id})

    async def delete_file(self, unique_id):
        return await self.files.delete_one({'unique_id': unique_id})

    async def total_files_count(self):
        return await self.files.count_documents({})

def get_readable_time(seconds: int) -> str:
    periods = [
        ('d', 60*60*24),
        ('h', 60*60),
        ('m', 60),
        ('s', 1)
    ]
    
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f'{int(period_value)}{period_name}')
    
    return ' '.join(result) if result else '0s'

def encode_file_id(file_id: str) -> str:
    return base64.urlsafe_b64encode(file_id.encode()).decode().rstrip("=")

def decode_file_id(encoded_id: str) -> str:
    padding = 4 - len(encoded_id) % 4
    if padding != 4:
        encoded_id += '=' * padding
    return base64.urlsafe_b64decode(encoded_id.encode()).decode()

async def is_user_joined(client: Client, user_id: int, channel) -> bool:
    if channel == "0" or channel == 0:
        return True

    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status != enums.ChatMemberStatus.BANNED
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Error checking user membership: {e}")
        return True

def get_file_type(message: Message) -> str:
    if message.document:
        return "document"
    elif message.video:
        return "video"
    elif message.audio:
        return "audio"
    elif message.photo:
        return "photo"
    elif message.voice:
        return "voice"
    elif message.video_note:
        return "video_note"
    elif message.sticker:
        return "sticker"
    elif message.animation:
        return "animation"
    else:
        return "unknown"

async def get_file_id_and_ref(message: Message) -> tuple:
    file_type = get_file_type(message)

    if file_type == "document":
        return message.document.file_id, message.document.file_unique_id
    elif file_type == "video":
        return message.video.file_id, message.video.file_unique_id
    elif file_type == "audio":
        return message.audio.file_id, message.audio.file_unique_id
    elif file_type == "photo":
        return message.photo.file_id, message.photo.file_unique_id
    elif file_type == "voice":
        return message.voice.file_id, message.voice.file_unique_id
    elif file_type == "video_note":
        return message.video_note.file_id, message.video_note.file_unique_id
    elif file_type == "sticker":
        return message.sticker.file_id, message.sticker.file_unique_id
    elif file_type == "animation":
        return message.animation.file_id, message.animation.file_unique_id

    return None, None

Bot = Client(
    "FileShareBot",
    api_id=Config.APP_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=50,
    sleep_threshold=10
)

db = Database(Config.DB_URL, Config.DB_NAME)
BOT_START_TIME = time.time()

@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id

    await db.add_user(
        user_id=user_id,
        first_name=message.from_user.first_name,
        username=message.from_user.username
    )

    if len(message.command) > 1:
        encoded_file_id = message.command[1]

        if Config.FORCE_SUB_CHANNEL != "0" and Config.FORCE_SUB_CHANNEL != 0:
            is_joined = await is_user_joined(client, user_id, Config.FORCE_SUB_CHANNEL)

            if not is_joined:
                try:
                    invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
                    force_text = Config.FORCE_SUB_MESSAGE.format(
                        first=message.from_user.first_name,
                        last=message.from_user.last_name or "",
                        username=message.from_user.username or "No Username",
                        mention=message.from_user.mention,
                        id=message.from_user.id,
                        channel=str(Config.FORCE_SUB_CHANNEL).replace("-100", "")
                    )

                    buttons = [[
                        InlineKeyboardButton("ðŸ“¢ Join Channel", url=invite_link.invite_link)
                    ],[
                        InlineKeyboardButton("ðŸ”„ Try Again", callback_data=f"check_sub:{encoded_file_id}")
                    ]]

                    await message.reply_text(
                        force_text,
                        reply_markup=InlineKeyboardMarkup(buttons),
                        quote=True
                    )
                    return
                except Exception as e:
                    logger.error(f"Error creating invite link: {e}")

        await send_file(client, message, encoded_file_id)

    else:
        start_text = Config.START_MESSAGE.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=message.from_user.username or "No Username",
            mention=message.from_user.mention,
            id=message.from_user.id
        )

        buttons = [[
            InlineKeyboardButton("ðŸ“¢ Updates", url="https://t.me/JishuBotz"),
            InlineKeyboardButton("ðŸ’¬ Support", url="https://t.me/JishuDeveloper")
        ]]

        await message.reply_text(
            start_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )

async def send_file(client: Client, message: Message, encoded_file_id: str):
    try:
        decoded_ids = decode_file_id(encoded_file_id).split("-")

        if len(decoded_ids) == 1:
            file_id = int(decoded_ids[0])

            try:
                msg = await client.get_messages(Config.CHANNEL_ID, file_id)

                if not msg:
                    await message.reply_text("âŒ File not found!")
                    return

                caption = msg.caption
                if Config.CUSTOM_CAPTION and msg.document:
                    caption = Config.CUSTOM_CAPTION.format(
                        filename=msg.document.file_name,
                        previouscaption=msg.caption or ""
                    )

                sent_msg = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    protect_content=Config.PROTECT_CONTENT,
                    reply_markup=msg.reply_markup if not Config.DISABLE_CHANNEL_BUTTON else None
                )

                if Config.FILE_AUTO_DELETE > 0:
                    await asyncio.sleep(Config.FILE_AUTO_DELETE)
                    try:
                        await sent_msg.delete()
                        await message.delete()
                    except:
                        pass

            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await message.reply_text(f"âŒ Error sending file: {str(e)}")

        else:
            start_id = int(decoded_ids[0])
            end_id = int(decoded_ids[1])

            batch_messages = []
            for msg_id in range(start_id, end_id + 1):
                try:
                    msg = await client.get_messages(Config.CHANNEL_ID, msg_id)
                    if msg and (msg.document or msg.video or msg.audio or msg.photo):
                        batch_messages.append(msg)
                except:
                    continue

            if not batch_messages:
                await message.reply_text("âŒ No files found!")
                return

            for msg in batch_messages:
                caption = msg.caption
                if Config.CUSTOM_CAPTION and msg.document:
                    caption = Config.CUSTOM_CAPTION.format(
                        filename=msg.document.file_name,
                        previouscaption=msg.caption or ""
                    )

                sent_msg = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    protect_content=Config.PROTECT_CONTENT,
                    reply_markup=msg.reply_markup if not Config.DISABLE_CHANNEL_BUTTON else None
                )

                await asyncio.sleep(1)

            if Config.FILE_AUTO_DELETE > 0:
                await asyncio.sleep(Config.FILE_AUTO_DELETE)
                try:
                    await message.delete()
                except:
                    pass

    except Exception as e:
        logger.error(f"Error in send_file: {e}")
        await message.reply_text("âŒ An error occurred while processing your request.")

@Bot.on_message(filters.command("users") & filters.user(Config.ADMINS))
async def users_command(client: Client, message: Message):
    total = await db.total_users_count()
    await message.reply_text(f"ðŸ‘¥ Total Users: {total}")

@Bot.on_message(filters.command("broadcast") & filters.user(Config.ADMINS) & filters.reply)
async def broadcast_command(client: Client, message: Message):
    broadcast_msg = message.reply_to_message

    users = await db.get_all_users()
    total = len(users)
    success = 0
    failed = 0

    status_msg = await message.reply_text("ðŸ“¡ Broadcasting...")

    for user in users:
        try:
            await broadcast_msg.copy(user['id'])
            success += 1
        except (UserIsBlocked, InputUserDeactivated):
            failed += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await broadcast_msg.copy(user['id'])
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"âœ… Broadcast Completed!\n\n"
        f"Total Users: {total}\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )

@Bot.on_message(filters.command("stats") & filters.user(Config.ADMINS))
async def stats_command(client: Client, message: Message):
    uptime = get_readable_time(int(time.time() - BOT_START_TIME))
    total_users = await db.total_users_count()
    total_files = await db.total_files_count()

    stats_text = Config.BOT_STATS_TEXT.format(
        uptime=uptime,
        users=total_users,
        files=total_files
    )

    await message.reply_text(stats_text)

@Bot.on_message(filters.command("batch") & filters.user(Config.ADMINS) & filters.private)
async def batch_command(client: Client, message: Message):
    if len(message.command) < 3:
        await message.reply_text(
            "ðŸ“ Usage:\n\n"
            "/batch [first_message_id] [last_message_id]\n\n"
            "Example: /batch 100 150"
        )
        return

    try:
        first_id = int(message.command[1])
        last_id = int(message.command[2])

        if first_id > last_id:
            await message.reply_text("âŒ First ID must be less than Last ID!")
            return

        try:
            await client.get_messages(Config.CHANNEL_ID, first_id)
            await client.get_messages(Config.CHANNEL_ID, last_id)
        except Exception as e:
            await message.reply_text(f"âŒ Error: Invalid message IDs!\n{str(e)}")
            return

        encoded = encode_file_id(f"{first_id}-{last_id}")
        bot_username = (await client.get_me()).username
        link = f"https://t.me/{bot_username}?start={encoded}"

        await message.reply_text(
            f"âœ… **Batch Link Generated!**\n\n"
            f"ðŸ“Š Total Messages: {last_id - first_id + 1}\n"
            f"ðŸ”— Link: `{link}`",
            quote=True
        )

    except Exception as e:
        logger.error(f"Error in batch command: {e}")
        await message.reply_text(f"âŒ Error: {str(e)}")

@Bot.on_message(filters.command("genlink") & filters.user(Config.ADMINS) & filters.private)
async def genlink_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "ðŸ“ Usage:\n\n"
            "/genlink [message_id]\n\n"
            "Example: /genlink 100"
        )
        return

    try:
        msg_id = int(message.command[1])

        try:
            msg = await client.get_messages(Config.CHANNEL_ID, msg_id)
            if not msg:
                raise Exception("Message not found")
        except Exception as e:
            await message.reply_text(f"âŒ Error: Invalid message ID!\n{str(e)}")
            return

        encoded = encode_file_id(str(msg_id))
        bot_username = (await client.get_me()).username
        link = f"https://t.me/{bot_username}?start={encoded}"

        await message.reply_text(
            f"âœ… **Link Generated!**\n\n"
            f"ðŸ”— Link: `{link}`",
            quote=True
        )

    except Exception as e:
        logger.error(f"Error in genlink command: {e}")
        await message.reply_text(f"âŒ Error: {str(e)}")

@Bot.on_message(filters.command("id"))
async def id_command(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    text = f"ðŸ‘¤ Your User ID: `{user_id}`\n"

    if message.chat.type != enums.ChatType.PRIVATE:
        text += f"ðŸ’¬ Chat ID: `{chat_id}`\n"

    if message.reply_to_message:
        reply_user_id = message.reply_to_message.from_user.id
        text += f"ðŸ‘¤ Replied User ID: `{reply_user_id}`"

    await message.reply_text(text, quote=True)

@Bot.on_message(filters.channel & filters.chat(Config.CHANNEL_ID))
async def save_file(client: Client, message: Message):
    try:
        file_type = get_file_type(message)
        if file_type == "unknown":
            return

        file_id, unique_id = await get_file_id_and_ref(message)

        if file_id and unique_id:
            await db.add_file(file_id, unique_id, message.caption)
            logger.info(f"File saved: {file_id}")

            msg_id = message.id
            encoded = encode_file_id(str(msg_id))
            bot_username = (await client.get_me()).username
            share_link = f"https://t.me/{bot_username}?start={encoded}"

            file_name = "File"
            file_size = ""

            if message.document:
                file_name = message.document.file_name or "Document"
                file_size = f"\nðŸ“¦ Size: {message.document.file_size / (1024*1024):.2f} MB"
            elif message.video:
                file_name = message.video.file_name or "Video"
                file_size = f"\nðŸ“¦ Size: {message.video.file_size / (1024*1024):.2f} MB"
            elif message.audio:
                file_name = message.audio.file_name or message.audio.title or "Audio"
                file_size = f"\nðŸ“¦ Size: {message.audio.file_size / (1024*1024):.2f} MB"
            elif message.photo:
                file_name = "Photo"
                file_size = f"\nðŸ“¦ Size: {message.photo.file_size / (1024*1024):.2f} MB"

            link_message = (
                f"âœ… **Link Generated!**\n\n"
                f"ðŸ“„ File: `{file_name}`{file_size}\n"
                f"ðŸ†” Message ID: `{msg_id}`\n\n"
                f"ðŸ”— **Share Link:**\n`{share_link}`"
            )

            await message.reply_text(
                link_message,
                quote=True,
                disable_web_page_preview=True
            )

            try:
                await client.send_message(
                    Config.OWNER_ID,
                    f"ðŸ”” **New File Added!**\n\n{link_message}",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Could not send notification to owner: {e}")

    except Exception as e:
        logger.error(f"Error saving file: {e}")
        traceback.print_exc()

@Bot.on_message(filters.private & filters.incoming)
async def default_handler(client: Client, message: Message):
    if message.text and message.text.startswith('/'):
        return

    await message.reply_text(Config.USER_REPLY_TEXT, quote=True)

@Bot.on_callback_query(filters.regex(r"^check_sub:"))
async def check_sub_callback(client: Client, query: CallbackQuery):
    encoded_file_id = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    is_joined = await is_user_joined(client, user_id, Config.FORCE_SUB_CHANNEL)

    if is_joined:
        await query.answer("âœ… Subscription verified!", show_alert=True)
        await query.message.delete()

        class DummyMessage:
            def __init__(self, user, client):
                self.from_user = user
                self.chat = user
                self.client = client

            async def reply_text(self, text, **kwargs):
                return await client.send_message(self.from_user.id, text)

            async def delete(self):
                pass

        dummy_msg = DummyMessage(query.from_user, client)
        await send_file(client, dummy_msg, encoded_file_id)

    else:
        await query.answer("âŒ You haven't joined yet!", show_alert=True)

async def main():
    await start_health_server()

    await Bot.start()
    logger.info("Bot started successfully!")
    logger.info("âœ¨ Automatic link generation enabled!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    logger.info("Bot starting...")

    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        sys.exit(1)

    if not Config.API_HASH or Config.APP_ID == 0:
        logger.error("API_HASH or APP_ID not found!")
        sys.exit(1)

    if Config.CHANNEL_ID == 0:
        logger.error("CHANNEL_ID not found!")
        sys.exit(1)

    if not Config.DB_URL:
        logger.error("DB_URL not found!")
        sys.exit(1)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped!")
