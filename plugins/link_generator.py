from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS
from helper_func import encode, get_message_id, short_url

@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    while True:
        try:
            first_message = await client.ask(
                text="Forward First Message From DB Channel or Send DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        
        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("This Forwarded Post is not from DB Channel", quote=True)
    
    while True:
        try:
            second_message = await client.ask(
                text="Forward Last Message From DB Channel or Send DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        
        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("This Forwarded Post is not from DB Channel", quote=True)
    
    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    short_link = short_url(link)
    
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Share Link", url=f'https://telegram.me/share/url?url={short_link}')]])
    
    await second_message.reply_text(f"Batch Link Generated: {short_link}", quote=True, reply_markup=reply_markup, disable_web_page_preview=True)

@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):
    while True:
        try:
            channel_message = await client.ask(
                text="Forward Message From DB Channel or Send DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("This Forwarded Post is not from DB Channel", quote=True)
    
    base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
    link = f"https://t.me/{client.username}?start={base64_string}"
    short_link = short_url(link)
    
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Share Link", url=f'https://telegram.me/share/url?url={short_link}')]])
    
    await channel_message.reply_text(f"Link Generated: {short_link}", quote=True, reply_markup=reply_markup, disable_web_page_preview=True)
