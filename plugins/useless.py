from bot import Bot
from pyrogram.types import Message
from pyrogram import filters
from config import ADMINS
from datetime import datetime
from helper_func import get_readable_time

@Bot.on_message(filters.command('stats') & filters.user(ADMINS))
async def stats(bot: Bot, message: Message):
    now = datetime.now()
    delta = now - bot.uptime
    time = get_readable_time(delta.seconds)
    await message.reply(f"📊 Bot Stats

⏰ Uptime: {time}")
