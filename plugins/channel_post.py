import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified
from bot import Bot
from config import ADMINS, DISABLE_CHANNEL_BUTTON
from helper_func import encode
import os

# ---------------- SET DB CHANNEL FROM ENV ----------------
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # Render env variable

if CHANNEL_ID == 0:
    print("⚠️ Warning: CHANNEL_ID not set in ENV!")

# Assign db_channel to Bot at startup
async def set_db_channel():
    if CHANNEL_ID != 0:
        Bot.db_channel = type("Channel", (), {"id": CHANNEL_ID})()
        print(f"✅ Bot db_channel set to {CHANNEL_ID}")
    else:
        print("⚠️ db_channel not set!")

asyncio.create_task(set_db_channel())

# ---------------- SAFE CHANNEL POST ----------------
@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','users','broadcast','batch','genlink','stats']))
async def channel_post(client: Client, message: Message):
    reply_text = await message.reply_text("Please Wait...!", quote=True)

    if not getattr(client, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        return

    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.x)
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except Exception as e:
        print(e)
        try:
            await reply_text.edit_text("Something Went Wrong..!")
        except MessageNotModified:
            pass
        return

    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]]
    )

    try:
        await reply_text.edit(
            "<b>Here Is Your Link</b>\n\n" + link,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except MessageNotModified:
        pass

    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except Exception as e:
            print("Edit Reply Markup Failed:", e)
            pass

# ---------------- AUTO UPDATE CHANNEL POSTS ----------------
@Bot.on_message(filters.channel & filters.incoming)
async def new_post(client: Client, message: Message):
    if DISABLE_CHANNEL_BUTTON or not getattr(client, "db_channel", None):
        return

    converted_id = message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]]
    )

    try:
        await message.edit_reply_markup(reply_markup)
    except Exception as e:
        print("Edit Reply Markup Failed:", e)
        pass

# Jishu Developer 
# Don't Remove Credit 🥺
# Telegram Channel @Madflix_Bots
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
