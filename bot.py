from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime
from config import (
    API_HASH, API_ID, LOGGER, BOT_TOKEN, 
    TG_BOT_WORKERS, FORCE_SUB_CHANNEL, CHANNEL_ID
)
import pyrogram.utils

# Avoid min channel id errors
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=TG_BOT_WORKERS,
            plugins={"root": "plugins"}
        )
        self.LOGGER = LOGGER
        self.uptime = None
        self.username = None
        self.invitelink = None
        self.db_channel = None

    async def start_forever(self):
        """
        Start bot and keep it running forever.
        Use this in bot_runner.py
        """
        await super().start()
        self.uptime = datetime.now()

        # Bot username
        me = await self.get_me()
        self.username = me.username

        # Force subscription check
        if FORCE_SUB_CHANNEL:
            try:
                chat = await self.get_chat(FORCE_SUB_CHANNEL)
                link = chat.invite_link
                if not link:
                    await self.export_chat_invite_link(FORCE_SUB_CHANNEL)
                    link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                self.invitelink = link
            except Exception as e:
                self.LOGGER(__name__).warning(e)
                self.LOGGER(__name__).warning(
                    "Bot Can't Export Invite link From Force Sub Channel!"
                )
                sys.exit()

        # DB channel check
        try:
            db_chat = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_chat
            test = await self.send_message(chat_id=db_chat.id, text="Hey 🖐")
            await test.delete()
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            self.LOGGER(__name__).warning(
                f"Make Sure Bot Is Admin In DB Channel, Current CHANNEL_ID: {CHANNEL_ID}"
            )
            sys.exit()

        # Set parse mode
        self.set_parse_mode(ParseMode.HTML)

        # Log start info
        self.LOGGER(__name__).info(
            f"Bot Running...!\nCreated By https://t.me/Madflix_Bots"
        )

        # Keep the bot alive until manually stopped
        await self.idle()

    async def stop_bot(self):
        """Stop the bot cleanly"""
        await super().stop()
        self.LOGGER(__name__).info("Bot Stopped...")
