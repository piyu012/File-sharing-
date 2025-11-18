import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified
from bot import Bot
from config import ADMINS, CHANNEL_ID, DISABLE_CHANNEL_BUTTON
from helper_func import encode

# ---------------- SAFE CHANNEL POST ----------------

@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','users','broadcast','batch','genlink','stats']))
async def channel_post(client: Client, message: Message):
    reply_text = await message.reply_text("Please Wait...!", quote=True)

    # Check if db_channel exists
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

    # Generate deep link
    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]]
    )

    # Send final link
    try:
        await reply_text.edit(
            "<b>Here Is Your Link</b>\n\n" + link,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except MessageNotModified:
        pass

    # Edit channel post reply_markup if not disabled
    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except Exception as e:
            print("Edit Reply Markup Failed:", e)
            pass


# ---------------- AUTO UPDATE CHANNEL POSTS ----------------
@Bot.on_message(filters.channel & filters.incoming & filters.chat(CHANNEL_ID))
async def new_post(client: Client, message: Message):

    if DISABLE_CHANNEL_BUTTON:
        return

    # Ensure db_channel exists
    if not getattr(client, "db_channel", None):
        print("⚠️ db_channel not set for channel post update")
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
