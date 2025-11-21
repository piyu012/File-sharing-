import asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import ADMINS
from helper_func import encode

@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','users','stats','broadcast']))
async def channel_post(client: Bot, message: Message):
    reply_text = await message.reply("⏳ Processing...", quote=True)
    
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except Exception as e:
        return await reply_text.edit_text(f"❌ Error: {e}")
    
    string = f"get-{post_message.id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    
    text = (
        "✅ **Link Generated!**\n\n"
        f"📎 `{link}`\n\n"
        f"📊 Msg ID: `{post_message.id}`"
    )
    
    await reply_text.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={link}")]
        ])
    )
