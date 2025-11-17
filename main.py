import asyncio
from fastapi import FastAPI
from bot import Bot

api = FastAPI()
bot = Bot()

@api.on_event("startup")
async def startup():
    # Start old bot in background
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown():
    # Graceful stop
    await bot.stop()

# Optional: friendly homepage
@api.get("/")
async def home():
    return {"message": "Old bot running in background!"}
