# (c) @JishuDeveloper

import os
import sys
import asyncio
from pyrogram import Client

# Bot client initialization
Bot = Client(
    "Bot",
    bot_token=os.environ.get("BOT_TOKEN"),
    api_id=int(os.environ.get("API_ID")),
    api_hash=os.environ.get("API_HASH"),
    plugins=dict(root="plugins")
)

# Run the bot
Bot.run()
