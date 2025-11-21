from pyrogram import Client
from pyrogram.enums import ParseMode
from datetime import datetime
from config import API_HASH, API_ID, BOT_TOKEN, TG_BOT_WORKERS, FORCE_SUB_CHANNEL, CHANNEL_ID, LOGGER
import pyrogram.utils

pyrogram.utils.MIN_CHANNEL_ID = -1009999999999


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=API_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=BOT_TOKEN
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        self.start_time = datetime.now().timestamp()

        # Force Sub Channel Link
        if FORCE_SUB_CHANNEL:
            try:
                link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                if not link:
                    await self.export_chat_invite_link(FORCE_SUB_CHANNEL)
                    link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                self.invitelink = link
            except Exception as a:
                self.LOGGER.warning(a)
                self.LOGGER.warning("Bot can't export invite link from force sub channel!")
                self.invitelink = None

        # Test DB Channel
        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
            test = await self.send_message(chat_id=db_channel.id, text="Test Message")
            await test.delete()
        except Exception as e:
            self.LOGGER.warning(e)
            self.LOGGER.warning(
                f"Make sure bot is admin in DB Channel, and double check the CHANNEL_ID value: {CHANNEL_ID}"
            )
            self.LOGGER.info("Bot Stopped. Join @Madflix_Bots for support")
            exit()

        # 🔥 FIXED — This f-string was broken earlier
        self.LOGGER.info(
            f"Bot Running..! Created by @JishuDeveloper"
        )

        self.username = usr_bot_me.username

    async def stop(self, *args):
        await super().stop()
        self.LOGGER.info("Bot stopped.")
