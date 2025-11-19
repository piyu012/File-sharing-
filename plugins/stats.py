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
    uptime_str = get_readable_time(delta.seconds)

    # Triple quotes ka use karke multi-line string
    stats_text = f"""📊 Bot Stats

⏱ Uptime: {uptime_str}"""

    await message.reply(stats_text)
