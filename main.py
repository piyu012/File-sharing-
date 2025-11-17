import os
import asyncio
from bot import Bot
from ad_api import api
import uvicorn

async def start_all():
    bot = Bot()
    asyncio.create_task(bot.start())  # start Pyrogram bot

    config = uvicorn.Config(api, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(start_all())
