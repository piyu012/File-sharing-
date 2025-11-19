import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from bot import Bot
from config import ADMINS, DISABLE_CHANNEL_BUTTON
from helper_func import encode, short_url

@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','users','broadcast','batch','genlink','stats','id','redeem']))
async def channel_post(client: Client, message: Message):
    reply_text = await message.reply_text("Please Wait...", quote=True)
    
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.x)
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except Exception as e:
        await reply_text.edit_text(f"Error: {e}")
        return
    
    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    
    short_link = short_url(link)
    
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Share Link", url=f'https://telegram.me/share/url?url={short_link}')]])
    
    await reply_text.edit(f"Link Generated: {short_link}", reply_markup=reply_markup, disable_web_page_preview=True)
    
    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except:
            pass
