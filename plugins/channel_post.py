# channel_post.py
import asyncio, traceback
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from bot import bot
from config import ADMIN_ID, CHANNEL_ID
from helper_func import encode

ADMINS = [ADMIN_ID] if ADMIN_ID else []

@bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','genlink']))
async def channel_post(client, message):
    reply = await message.reply_text("Please wait...", quote=True)

    # ensure channel configured
    if CHANNEL_ID == 0:
        await reply.edit_text("⚠️ CHANNEL_ID not set in ENV. Contact admin.")
        return

    # ensure bot has channel
    if not getattr(bot, "db_channel", None):
        try:
            # try to fetch channel object
            bot.db_channel = await bot.get_chat(CHANNEL_ID)
            print("Loaded db_channel:", bot.db_channel.id)
        except Exception as e:
            print("Failed to load db_channel:", e)
            await reply.edit_text("⚠️ Unable to access channel. Check bot permissions.")
            return

    try:
        post = await message.copy(chat_id=bot.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.x)
        post = await message.copy(chat_id=bot.db_channel.id, disable_notification=True)
    except Exception as e:
        traceback.print_exc()
        await reply.edit_text("Something Went Wrong..! (copy failed)")
        return

    converted = post.id * abs(bot.db_channel.id)
    token_str = f"file-{converted}"
    b64 = await encode(token_str)
    link = f"https://t.me/{bot.username}?start={b64}"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f"https://telegram.me/share/url?url={link}")]])

    try:
        await reply.edit_text(f"<b>Here Is Your Link</b>\n\n{link}", reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass

    # try edit post buttons
    try:
        await post.edit_reply_markup(kb)
    except Exception as e:
        print("edit_reply_markup failed:", e)
