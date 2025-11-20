import os
import time
import hmac
import hashlib
import asyncio
import base64

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import (
    ADMINS,
    START_MSG,
    CUSTOM_CAPTION,
    DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT,
    FILE_AUTO_DELETE,
    HMAC_SECRET,
    BASE_URL
)
from helper_func import subscribed, encode, decode, get_messages
from database import add_user, del_user, full_userbase, present_user

# Token system
from db_init import has_valid_token, create_token


# ----------------------------- UTILS ----------------------------- #

def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def short_adrinolinks(long_url: str) -> str:
    from config import ADRINO_API
    import requests
    
    if not ADRINO_API:
        return long_url

    try:
        r = requests.get(f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}", timeout=10).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url


async def delete_file_later(client, message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass


# ----------------------------- START COMMAND ----------------------------- #

@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id

    # Add user to DB
    if not await present_user(uid):
        try:
            await add_user(uid)
        except:
            pass

    # If start has argument
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            
            if base64_string == "verified":
                await message.reply_text("Token verified successfully! You can now access files.")
                return

            decoded = await decode(base64_string)
            args = decoded.split("-")

            # Multi files
            if len(args) == 3:
                try:
                    start = int(int(args[1]) / abs(client.db_channel.id))
                    end = int(int(args[2]) / abs(client.db_channel.id))
                    ids = range(start, end + 1)
                except:
                    return

            # Single file
            elif len(args) == 2:
                try:
                    ids = [int(int(args[1]) / abs(client.db_channel.id))]
                except:
                    return

            else:
                return

            # Check token
            if not await has_valid_token(uid):
                ts = int(time.time())
                payload = f"{uid}:{ts}"
                sig = sign(payload)

                await create_token(uid, payload, sig)

                encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
                url = f"{BASE_URL}/watch?data={encoded}"
                short = short_adrinolinks(url)

                await message.reply_text(
                    f"⚠️ Access Locked!\n\nWatch Ad to unlock:\n{short}\n\nToken valid for 12 hours.",
                    disable_web_page_preview=True
                )
                return

            # Send files
            temp_msg = await message.reply("Please wait...")

            try:
                msgs = await get_messages(client, ids)
            except:
                await message.reply_text("Something went wrong!")
                await temp_msg.delete()
                return

            await temp_msg.delete()

            for msg in msgs:
                caption = ""

                if CUSTOM_CAPTION and msg.document:
                    caption = CUSTOM_CAPTION.format(
                        previouscaption=msg.caption.html if msg.caption else "",
                        filename=msg.document.file_name
                    )
                else:
                    caption = msg.caption.html if msg.caption else ""

                reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None

                try:
                    copied = await msg.copy(
                        chat_id=uid,
                        caption=caption,
                        parse_mode='html',
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )

                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))

                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    continue
                except:
                    continue

            return

        except:
            pass

    # Default start message
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("About", callback_data="about"),
                InlineKeyboardButton("Close", callback_data="close")
            ]
        ]
    )

    await message.reply_text(
        START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username='@' + message.from_user.username if message.from_user.username else None,
            mention=message.from_user.mention,
            id=uid
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )


# ----------------------------- USERS COUNT ----------------------------- #

@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(message.chat.id, "Processing...")
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")


# ----------------------------- BROADCAST ----------------------------- #

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):

    if not message.reply_to_message:
        msg = await message.reply("Please reply to a message to broadcast!")
        await asyncio.sleep(8)
        await msg.delete()
        return

    query = await full_userbase()
    broadcast_msg = message.reply_to_message

    total = successful = blocked = deleted = unsuccessful = 0

    pls_wait = await message.reply("Broadcasting message...")

    for chat_id in query:
        try:
            await broadcast_msg.copy(chat_id)
            successful += 1

        except FloodWait as e:
            await asyncio.sleep(e.x)
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except:
                unsuccessful += 1

        except UserIsBlocked:
            await del_user(chat_id)
            blocked += 1

        except InputUserDeactivated:
            await del_user(chat_id)
            deleted += 1

        except:
            unsuccessful += 1

        total += 1

    status = (
        f"Successful: {successful}\n"
        f"Blocked: {blocked}\n"
        f"Deleted: {deleted}\n"
        f"Unsuccessful: {unsuccessful}\n"
        f"Total: {total}"
    )

    await pls_wait.edit(status)
