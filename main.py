import asyncio
from fastapi import FastAPI
from bot import bot
from routes.watch import router as watch_router
from routes.callback import router as callback_router
# main.py me bot start hone se pehle
from handlers import link_generator  # ya jaha bhi file rakhi hai

api = FastAPI()

api.include_router(watch_router)
api.include_router(callback_router)

@api.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()
