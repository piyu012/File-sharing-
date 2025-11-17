import asyncio
from bot import Bot
from ad_api import api   # FastAPI instance
import uvicorn


async def start_all():
    bot = Bot()

    # Start Pyrogram bot
    asyncio.create_task(bot.start())

    # Start FastAPI server
    config = uvicorn.Config(api, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(start_all())
