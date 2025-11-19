from pyrogram import __version__
from bot import Bot
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    
    if data == "about":
        text = f"Bot Name: File Sharing Bot

Language: Python 3

Library: Pyrogram {__version__}

Server: Render

Developer: @JishuDeveloper"
        await query.message.edit_text(text=text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close")]]))
    
    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
