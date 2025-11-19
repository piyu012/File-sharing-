import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from bot import Bot

bot = Bot()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[STARTUP] Starting Pyrogram bot...")
    await bot.start()
    print("[STARTUP] Bot started successfully!")
    try:
        yield
    finally:
        print("[SHUTDOWN] Stopping bot...")
        await bot.stop()
        print("[SHUTDOWN] Bot stopped.")

api = FastAPI(lifespan=lifespan)

@api.get("/")
async def root():
    return {"status": "Bot is running", "bot": "File Sharing + Token System"}

@api.get("/health")
async def health():
    return {"status": "ok"}
