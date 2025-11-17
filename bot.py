import asyncio
import threading
from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import (
    API_HASH, API_ID, LOGGER, BOT_TOKEN,
    TG_BOT_WORKERS, FORCE_SUB_CHANNEL, CHANNEL_ID
)

import pyrogram.utils
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999


# -------------------------
# FASTAPI APP FOR TOKEN API
# -------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOKEN_DB = {}  # memory database


@app.get("/get-token")
def get_token(user_id: int):
    token = TOKEN_DB.get(user_id)
    return {"token": token}


@app.post("/save-token")
def save_token(user_id: int, token: str):
    TOKEN_DB[user_id] = token
    return {"status": "saved"}


def start_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000)


# -------------------------
#     PYROGRAM BOT
# -------------------------

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()

        # Force Sub Check
        if FORCE_SUB_CHANNEL:
            try:
                link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                if not link:
                    await self.export_chat_invite_link(FORCE_SUB_CHANNEL)
                    link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                self.invitelink = link
            except Exception as a:
                self.LOGGER(__name__).warning(a)
                sys.exit()

        # DB Channel Check
        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
            msg = await self.send_message(CHANNEL_ID, "DB Connected ✔")
            await msg.delete()
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            sys.exit()

        self.set_parse_mode(ParseMode.HTML)
        self.username = usr_bot_me.username
        self.LOGGER(__name__).info("Bot Started ✔")

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped")


# Run Bot + FastAPI together
if __name__ == "__main__":

    # Start FastAPI in separate thread
    threading.Thread(target=start_fastapi).start()

    # Start Pyrogram bot
    bot = Bot()
    bot.run()
