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
    ADMINS, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT,
    FILE_AUTO_DELETE, HMAC_SECRET, BASE_URL, ADRINO_API
)
from helper_func import subscribed, encode, decode, get_messages
from db_init import add_user, full_userbase, present_user, has_valid_token, create_token

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -------------------------
# HMAC SIGN
# -------------------------
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


# -------------------------
# ADRINO SHORTENER
# -------------------------
def short_adrinolinks(long_url: str) -> str:
    if not ADRINO_API or ADRINO_API == "None":
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
    except:
        pass
    return long_url


# -------------------------
# AUTO DELETE
# -------------------------
async def delete_file_later(client: Bot, message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# -------------------------
# START COMMAND
# -------------------------
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):

    uid = message.from_user.id

    # Register new user
    if not await present_user(uid):
        await add_user(uid)

    # Check if link contains encoded file ID
    if len(message.text.split()) > 1:

        # Decode file request
        try:
            encoded = message.text.split(" ", 1)[1]
            decoded = await decode(encoded)
            parts = decoded.split("-")
        except:
            return await message.reply("❌ Invalid link!")

        # Determine single or batch links
        try:
            if len(parts) == 2:
                ids = [int(parts[1])]
            elif len(parts) == 3:
                ids = list(range(int(parts[1]), int(parts[2]) + 1))
            else:
                return await message.reply("❌ Invalid link format!")
        except:
            return await message.reply("❌ Invalid file ID!")

        # Token check
        if not await has_valid_token(uid):
            payload = f"{uid}:{int(time.time())}"
            sig = sign(payload)

            await create_token(uid, payload, sig, expire_hours=12)

            encoded_payload = base64.urlsafe_b64encode(payload.encode()).decode()
            token_url = f"{BASE_URL}/ad?payload={encoded_payload}&sig={sig}"

            short = short_adrinolinks(token_url)

            return await message.reply(
                (
                    "⚠️ **Token Required!**\n\n"
                    "Your access token has expired.\n"
                    "Verify once and unlock files for **12 hours**.\n\n"
                    f"🔗 Click here: {short}"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Generate Token", url=short)]
                ])
            )

        # Fetch files
        wait = await message.reply("⏳ Fetching...")

        try:
            msgs = await get_messages(client, ids)
        except:
            await wait.delete()
            return await message.reply("❌ File not found or deleted.")

        await wait.delete()

        sent = 0
        failed = 0

        # Send files
        for msg in msgs:
            if not msg:
                failed += 1
                continue

            # Caption
            if CUSTOM_CAPTION:
                filename = (
                    msg.document.file_name if msg.document else
                    msg.video.file_name if msg.video else
                    "File"
                )
                caption = CUSTOM_CAPTION.format(
                    previouscaption=msg.caption.html if msg.caption else "",
                    filename=filename
                )
            else:
                caption = msg.caption.html if msg.caption else ""

            try:
                sent_msg = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    parse_mode="html",
                    reply_markup=None if DISABLE_CHANNEL_BUTTON else msg.reply_markup,
                    protect_content=PROTECT_CONTENT
                )
                sent += 1

                if FILE_AUTO_DELETE:
                    asyncio.create_task(delete_file_later(client, sent_msg, FILE_AUTO_DELETE))

            except FloodWait as e:
                await asyncio.sleep(e.value)
            except:
                failed += 1

        summary = (
            f"✅ Sent: {sent}\n"
            f"⚠️ Failed: {failed}\n"
            f"🗑 Auto-delete: {FILE_AUTO_DELETE}s" if FILE_AUTO_DELETE else f"✅ Sent: {sent}"
        )

        return await message.reply(summary)

    # -------------------------
    # NORMAL START MESSAGE
    # -------------------------
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel", url="https://t.me/your_channel")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

    await message.reply(
        START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=f"@{message.from_user.username}" if message.from_user.username else "",
            mention=message.from_user.mention,
            id=uid
        ),
        reply_markup=btn,
        disable_web_page_preview=True
    )


# -------------------------
# USERS COMMAND
# -------------------------
@Bot.on_message(filters.command("users") & filters.user(ADMINS))
async def users_command(client: Bot, message: Message):
    users = await full_userbase()
    await message.reply(f"👥 Total Users: `{len(users)}`")


# -------------------------
# STATS COMMAND
# -------------------------
@Bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client: Bot, message: Message):
    users = await full_userbase()
    uptime = time.time() - getattr(client, "start_time", time.time())

    h = int(uptime // 3600)
    m = int((uptime % 3600) // 60)

    await message.reply(
        f"📊 **Bot Stats**\n\n"
        f"👥 Users: `{len(users)}`\n"
        f"⏰ Uptime: `{h}h {m}m`\n"
        f"🤖 Bot: @{client.username}"
    )
