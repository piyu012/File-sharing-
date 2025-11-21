import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from bot import Bot
from addon.ad_routes import router as ad_router

bot = Bot()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown bot with FastAPI"""
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

# Import ad routes
from addon.ad_routes import router as ad_router
api.include_router(ad_router)

# Root endpoint
@api.get("/")
async def root():
    return {"status": "Bot is running", "system": "File Sharing + Ad System"}

# Health check
@api.get("/health")
async def health():
    return {"status": "ok"}
