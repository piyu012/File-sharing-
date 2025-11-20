import os
import time
import hmac
import hashlib
import asyncio
import base64
import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------
# TOKEN SIGNING
# ------------------------------------
def sign(data: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


# ------------------------------------
# SHORTNER
# ------------------------------------
def short_adrinolinks(long_url: str) -> str:
    from config import ADRINO_API
    import requests

    if not ADRINO_API:
        return long_url

    try:
        r = requests.get(
            "https://adrinolinks.com/api",
            params={"api": ADRINO_API, "url": long_url},
            timeout=10
        )
        if r.status_code == 200:
            js = r.json()
            if js.get("status") == "success":
                return js.get("shortenedUrl", long_url)
    except Exception as e:
        logger.error(f"Shortener error: {e}")

    return long_url



# ------------------------------------
# DELETE FILE AFTER DELAY
# ------------------------------------
async def delete_file_later(client, message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# ------------------------------------
# START HANDLER
# ------------------------------------
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_handler(client: Bot, message: Message):
    uid = message.from_user.id

    if not await present_user(uid):
        await add_user(uid)

    # -------------------------------
    # LINK PARSER
    # -------------------------------
    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
        except:
            return await message.reply("❌ Invalid link!")

        try:
            decoded = await decode(base64_string)
            parts = decoded.split("-")
        except:
            return await message.reply("❌ Invalid or Corrupted Link!")

        # For batch
        if len(parts) == 3:
            try:
                start_id = int(int(parts[1]) / abs(client.db_channel.id))
                end_id = int(int(parts[2]) / abs(client.db_channel.id))
            except:
                return await message.reply("❌ Invalid batch link!")

            ids = range(start_id, end_id + 1)

        # Single
        elif len(parts) == 2:
            try:
                ids = [int(int(parts[1]) / abs(client.db_channel.id))]
            except:
                return await message.reply("❌ Invalid file link!")
        else:
            return await message.reply("❌ Invalid link format!")

        # -------------------------------
        # TOKEN CHECK
        # -------------------------------
        if not await has_valid_token(uid):
            payload = f"{uid}:{int(time.time())}"
            sig = sign(payload)
            await create_token(uid, payload, sig, expire_hours=12)

            enc_payload = base64.urlsafe_b64encode(payload.encode()).decode()
            ad_url = f"{BASE_URL}/ad?payload={enc_payload}&sig={sig}"
            short_url = short_adrinolinks(ad_url)

            return await message.reply_text(
                f"""⚠️ **Token Required!**

Your token is expired or invalid.

Please watch the ad to generate a new token.

Token is valid for **12 hours** after activation.

🔗 **Click to verify token:** {short_url}
""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Generate Token", url=short_url)]
                ]),
                disable_web_page_preview=True
            )

        # -------------------------------
        # SEND FILES
        # -------------------------------
        wait_msg = await message.reply("⏳ Fetching files...")

        try:
            msgs = await get_messages(client, ids)
        except Exception as e:
            await wait_msg.delete()
            return await message.reply("❌ Files not found!")

        await wait_msg.delete()

        sent = 0
        errors = 0

        for msg in msgs:
            if not msg:
                errors += 1
                continue

            # Caption Fix
            if CUSTOM_CAPTION:
                if msg.document:
                    name = msg.document.file_name
                elif msg.video:
                    name = msg.video.file_name or "Video"
                elif msg.photo:
                    name = "Photo"
                else:
                    name = "File"

                caption = CUSTOM_CAPTION.format(
                    previouscaption=msg.caption.html if msg.caption else "",
                    filename=name
                )
            else:
                caption = msg.caption.html if msg.caption else None

            reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None

            try:
                sent_msg = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    parse_mode="html",
                    reply_markup=reply_markup,
                    protect_content=PROTECT_CONTENT
                )
                sent += 1

                if FILE_AUTO_DELETE:
                    asyncio.create_task(delete_file_later(client, sent_msg, FILE_AUTO_DELETE))

            except FloodWait as e:
                await asyncio.sleep(e.x)
            except:
                errors += 1

        summary = f"✅ Sent: {sent}\n⚠️ Failed: {errors}"
        if FILE_AUTO_DELETE:
            summary += f"\n🗑 Auto delete in {FILE_AUTO_DELETE}s"

        return await message.reply(summary)

    # -------------------------------
    # NORMAL /START
    # -------------------------------
    await message.reply_text(
        START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=('@' + message.from_user.username) if message.from_user.username else None,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Channel", url="https://t.me/your_channel"),
                InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/your_dev"),
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                InlineKeyboardButton("📊 About", callback_data="about"),
            ]
        ]),
        disable_web_page_preview=True
    )



# ------------------------------------
# BROADCAST
# ------------------------------------
@Bot.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to message to broadcast!")

    users = await full_userbase()

    sent = 0
    blocked = 0
    deleted = 0
    failed = 0

    info = await message.reply("📢 Broadcasting...")

    for user in users:
        try:
            await message.reply_to_message.copy(user)
            sent += 1
        except UserIsBlocked:
            blocked += 1
            await del_user(user)
        except InputUserDeactivated:
            deleted += 1
            await del_user(user)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except:
            failed += 1

    await info.edit(
        f"📊 **Broadcast Finished**\n\n"
        f"✅ Sent: {sent}\n"
        f"🚫 Blocked: {blocked}\n"
        f"❌ Deleted: {deleted}\n"
        f"⚠ Failed: {failed}"
    )



# ------------------------------------
# STATS
# ------------------------------------
@Bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(client, message):
    users = await full_userbase()
    total = len(users)

    uptime = int(time.time() - client.start_time)
    hrs = uptime // 3600
    mins = (uptime % 3600) // 60

    await message.reply(
        f"📊 **Bot Stats**\n\n"
        f"👥 Users: {total}\n"
        f"⏱ Uptime: {hrs}h {mins}m\n"
        f"🤖 @{client.username}"
    )
