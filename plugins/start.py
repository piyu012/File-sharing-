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
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


# =====================================================
# SHORT LINK FUNCTION  (ADRINOLINKS)
# =====================================================
def short_adrinolinks(long_url: str) -> str:
    if not ADRINO_API:
        return long_url

    try:
        r = requests.get(
            "https://adrinolinks.com/api",
            params={"api": ADRINO_API, "url": long_url},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                return data.get("shortenedUrl", long_url)
    except Exception as e:
        logger.error(f"Shortener Error: {e}")

    return long_url


# =====================================================
# AUTO DELETE FUNCTION
# =====================================================
async def delete_file_later(client: Bot, message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# =====================================================
# /START COMMAND HANDLER
# =====================================================
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):

    uid = message.from_user.id

    # ADD USER TO DB
    if not await present_user(uid):
        await add_user(uid)

    # ========== FILE LINK HANDLING ==========
    if len(message.text.split()) > 1:

        # extract encoded string
        try:
            encoded = message.text.split(" ", 1)[1]
        except:
            return await message.reply("❌ Invalid link!")

        # decode
        try:
            decoded = await decode(encoded)
            parts = decoded.split("-")
        except:
            return await message.reply("❌ Corrupted link!")

        # batch links
        if len(parts) == 3:
            try:
                start_id = int(parts[1])
                end_id = int(parts[2])
            except:
                return await message.reply("❌ Invalid batch link!")

            # generate ID list
            ids = list(range(start_id, end_id + 1))

        # single file
        elif len(parts) == 2:
            try:
                ids = [int(parts[1])]
            except:
                return await message.reply("❌ Invalid file link!")

        else:
            return await message.reply("❌ Invalid link format!")

        # ========== TOKEN CHECK ==========
        if not await has_valid_token(uid):

            payload = f"{uid}:{int(time.time())}"
            sig = sign(payload)

            await create_token(uid, payload, sig, expire_hours=12)

            encoded_payload = base64.urlsafe_b64encode(payload.encode()).decode()
            token_url = f"{BASE_URL}/ad?payload={encoded_payload}&sig={sig}"

            try:
                short = short_adrinolinks(token_url)
            except:
                short = token_url

            return await message.reply(
                "⚠️ **Token Required!**\n\n"
                "Token expired or invalid. Please verify it.\n"
                "Token will be valid for **12 hours**.\n\n"
                f"🔗 Click here: {short}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Generate Token", url=short)]
                ])
            )

        # ========== FETCHING FILES ==========
        wait_msg = await message.reply("⏳ Fetching files...")

        try:
            msgs = await get_messages(client, ids)
        except Exception as e:
            logger.error(e)
            await wait_msg.delete()
            return await message.reply("❌ File not found! It may be deleted.")

        await wait_msg.delete()

        sent = 0
        failed = 0

        for msg in msgs:

            if not msg:
                failed += 1
                continue

            # ---------- CAPTION FIX ----------
            if CUSTOM_CAPTION:
                filename = "File"

                if msg.document:
                    filename = msg.document.file_name
                elif msg.video:
                    filename = msg.video.file_name or "Video"
                elif msg.audio:
                    filename = msg.audio.file_name or "Audio"
                elif msg.photo:
                    filename = "Photo"

                caption = CUSTOM_CAPTION.format(
                    previouscaption=msg.caption.html if msg.caption else "",
                    filename=filename
                )
            else:
                caption = msg.caption.html if msg.caption else ""

            # BUTTONS
            reply_markup = None if DISABLE_CHANNEL_BUTTON else msg.reply_markup

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

            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except Exception as e:
                logger.error(e)
                failed += 1

        # SUMMARY
        summary = f"✅ **Sent: {sent} file(s)**"
        if failed:
            summary += f"\n⚠️ Failed: {failed} file(s)"

        if FILE_AUTO_DELETE:
            summary += f"\n🗑 Auto delete: {FILE_AUTO_DELETE}s"

        return await message.reply(summary)

    # ======= NORMAL START MESSAGE (NO FILE LINK) =======
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
            username=f"@{message.from_user.username}" if message.from_user.username else "",
            mention=message.from_user.mention,
            id=uid
        ),
        reply_markup=btn
    )


# =====================================================
# ADMIN COMMANDS
# =====================================================
@Bot.on_message(filters.command("users") & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    users = await full_userbase()
    await message.reply(f"👥 **Total Users:** `{len(users)}`")


@Bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client: Bot, message: Message):
    uptime = time.time() - getattr(client, "start_time", time.time())
    h = int(uptime // 3600)
    m = int((uptime % 3600) // 60)

    await message.reply(
        f"📊 **Bot Stats**\n\n"
        f"👥 Users: `{len(await full_userbase())}`\n"
        f"⏰ Uptime: `{h}h {m}m`\n"
        f"🤖 Bot: @{client.username}"
    )
