# bot.py
from pyrogram import Client
from config import BOT_TOKEN, API_ID, API_HASH

# session name "fileshare"
bot = Client(
    "fileshare",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=32
)
