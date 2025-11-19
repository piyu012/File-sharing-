from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from pyrogram import Client, filters

bot = Client(
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

bot.db_channel = DB_CHANNEL
ADMINS = [ADMIN_ID]

# Keep a global task reference so it isn't GC'd
pyro_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pyro_task
    # Start Pyrogram and keep its update loop alive
    await bot.start()
    # optional: ensure a tiny heartbeat task to keep loop busy
    async def _ping():
        while True:
            await asyncio.sleep(3600)
    pyro_task = asyncio.create_task(_ping())
    try:
        yield
    finally:
        if pyro_task:
            pyro_task.cancel()
            with contextlib.suppress(Exception):
                await pyro_task
        await bot.stop()

api = FastAPI(lifespan=lifespan)
