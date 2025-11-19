from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import FORCE_SUB_CHANNEL, FORCE_MSG
from helper_func import is_subscribed

@Bot.on_message(filters.private & ~is_subscribed)
async def force_sub_handler(client: Bot, message: Message):
    if FORCE_SUB_CHANNEL:
        try:
            invite_link = client.invitelink
        except:
            invite_link = "https://t.me/your_channel"
        
        text = FORCE_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name if message.from_user.last_name else "",
            username="@" + message.from_user.username if message.from_user.username else "None",
            mention=message.from_user.mention,
            id=message.from_user.id
        )
        
        await message.reply_text(text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Channel", url=invite_link)]]), quote=True)
