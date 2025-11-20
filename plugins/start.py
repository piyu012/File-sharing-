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
    ADMINS, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT, FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL
)
from helper_func import subscribed, encode, decode, get_messages
from db_init import add_user, del_user, full_userbase, present_user, has_valid_token, create_token


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


@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id

    if not await present_user(uid):
        try:
            await add_user(uid)
        except:
            pass

    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]

            if base64_string == "verified":
                await message.reply_text("Token verified successfully! You can now access files.")
                return

            string = await decode(base64_string)
            argument = string.split("-")

            if len(argument) == 3:
                try:
                    start = int(int(argument[1]) / abs(client.db_channel.id))
                    end = int(int(argument[2]) / abs(client.db_channel.id))
                    ids = range(start, end + 1)
                except:
                    return

            elif len(argument) == 2:
                try:
                    ids = [int(int(argument[1]) / abs(client.db_channel.id))]
                except:
                    return

            else:
                return

            if not await has_valid_token(uid):
                ts = int(time.time())
                payload = f"{uid}:{ts}"
                sig = sign(payload)

                await create_token(uid, payload, sig)

                encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
                url = f"{BASE_URL}/watch?data={encoded}"
                short_url = short_adrinolinks(url)

                lock_text = "Access Locked!

Watch ad to unlock: " + short_url + "

Token valid for 12 hours after verification."
                await message.reply_text(lock_text, disable_web_page_preview=True)
                return

            temp_msg = await message.reply("Please wait...")

            try:
                messages = await get_messages(client, ids)
            except Exception as e:
                print(f"Error getting messages: {e}")
                await message.reply_text("Something went wrong! File not found.")
                await temp_msg.delete()
                return

            await temp_msg.delete()

            for idx, msg in enumerate(messages):

                if bool(CUSTOM_CAPTION) and bool(msg.document):
                    caption = CUSTOM_CAPTION.format(
                        previouscaption="" if not msg.caption else msg.caption.html,
                        filename=msg.document.file_name
                    )
                else:
                    caption = "" if not msg.caption else msg.caption.html

                reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None

                try:
                    copied = await msg.copy(
                        chat_id=uid,
                        caption=caption,
                        parse_mode="html",
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )

                    if FILE_AUTO_DELETE:
                        asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))

                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    try:
                        copied = await msg.copy(
                            chat_id=uid,
                            caption=caption,
                            parse_mode="html",
                            reply_markup=reply_markup,
                            protect_content=PROTECT_CONTENT
                        )
                        
                        if FILE_AUTO_DELETE:
                            asyncio.create_task(delete_file_later(client, copied, FILE_AUTO_DELETE))
                    except:
                        pass

                except Exception as e:
                    print(f"Error copying message {idx}: {e}")
                    pass

            return

        except Exception as e:
            print(f"Error in start command: {e}")
            pass

    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("About", callback_data="about"),
            InlineKeyboardButton("Close", callback_data="close")
        ]
    ])

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


@Bot.on_message(filters.command("users") & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text="Processing...")
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")


@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):

    if not message.reply_to_message:
        msg = await message.reply("Please Reply to a message to broadcast!")
        await asyncio.sleep(8)
        await msg.delete()
        return

    query = await full_userbase()
    broadcast_msg = message.reply_to_message

    total = successful = blocked = deleted = unsuccessful = 0

    pls_wait = await message.reply("Broadcasting Message...")

    for chat_id in query:
        try:
            await broadcast_msg.copy(chat_id)
            successful += 1

        except FloodWait as e:
            await asyncio.sleep(e.x)
            await broadcast_msg.copy(chat_id)
            successful += 1

        except UserIsBlocked:
            await del_user(chat_id)
            blocked += 1

        except InputUserDeactivated:
            await del_user(chat_id)
            deleted += 1

        except:
            unsuccessful += 1

        total += 1

    status = "Successful: " + str(successful) + "
Blocked: " + str(blocked) + "
Deleted: " + str(deleted) + "
Unsuccessful: " + str(unsuccessful) + "
Total: " + str(total)

    return await pls_wait.edit(status)
