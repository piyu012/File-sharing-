import asyncio
from fastapi import FastAPI
from addons.bot import bot
from addons.routes.watch import router as watch_router
from addons.routes.callback import router as callback_router

api = FastAPI()

api.include_router(watch_router)
api.include_router(callback_router)

@api.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()
