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


# ------------------------------
# TOKEN SIGNING
# ------------------------------
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


# ------------------------------
# SHORT LINK
# ------------------------------
def short_adrinolinks(long_url: str) -> str:
    from config import ADRINO_API
    import requests

    if not ADRINO_API:
        return long_url

    try:
        r = requests.get(
            f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}",
            timeout=10
        ).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url


# ------------------------------
# AUTO DELETE
# ------------------------------
async def delete_file_later(client, message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass


# ------------------------------
# START COMMAND (FIXED)
# ------------------------------
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):

    uid = message.from_user.id

    if not await present_user(uid):
        try:
            await add_user(uid)
        except:
            pass

    # ------------------------------
    # HANDLE ENCODED LINK
    # ------------------------------
    if len(message.text) > 7:

        try:
            base64_string = message.text.split(" ", 1)[1]
            decoded = await decode(base64_string)
            parts = decoded.split("-")

            # ------------ SINGLE FILE ------------
            if parts[0] == "get" and len(parts) == 2:
                ids = [int(parts[1])]

            # ------------ BATCH FILES ------------
            elif parts[0] == "get" and len(parts) == 3:
                start_id = int(parts[1])
                end_id = int(parts[2])
                ids = list(range(start_id, end_id + 1))

            else:
                return

        except Exception as e:
            print("Decode error:", e)
            return await message.reply("❌ Invalid link!", quote=True)

        # ------------------------------
        # TOKEN CHECK
        # ------------------------------
        if not await has_valid_token(uid):

            ts = int(time.time())
            payload = f"{uid}:{ts}"
            sig = sign(payload)

            await create_token(uid, payload, sig)

            encoded = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
            url = f"{BASE_URL}/watch?data={encoded}"

            short_url = short_adrinolinks(url)

            return await message.reply(
                f"🔒 **Access Locked!**\n\nWatch ad to unlock:\n{short_url}\n\nToken valid 12 hours.",
                disable_web_page_preview=True
            )

        # ------------------------------
        # SEND FILES
        # ------------------------------
        wait_msg = await message.reply("📥 Fetching files...")

        try:
            msgs = await get_messages(client, ids)
        except:
            await wait_msg.delete()
            return await message.reply("❌ File not found!", quote=True)

        await wait_msg.delete()

        for msg in msgs:

            caption = msg.caption.html if msg.caption else ""
            if CUSTOM_CAPTION and msg.document:
                caption = CUSTOM_CAPTION.format(
                    previouscaption=caption,
                    filename=msg.document.file_name
                )

            markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None

            try:
                sent = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode="html",
                    protect_content=PROTECT_CONTENT
                )

                if FILE_AUTO_DELETE:
                    asyncio.create_task(delete_file_later(client, sent, FILE_AUTO_DELETE))

            except FloodWait as e:
                await asyncio.sleep(e.x)
                try:
                    await msg.copy(uid)
                except:
                    pass

        return

    # ------------------------------
    # DEFAULT START MESSAGE
    # ------------------------------
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("About", callback_data="about"),
         InlineKeyboardButton("Close", callback_data="close")]
    ])

    await message.reply_text(
        START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=f"@{message.from_user.username}" if message.from_user.username else "",
            mention=message.from_user.mention,
            id=uid
        ),
        reply_markup=btn,
        disable_web_page_preview=True
    )
