import asyncio
import uvicorn
from addons.ad_api import bot, api  # FastAPI app + Pyrogram bot

async def start_bot():
    await bot.start()  # bot background me start

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    uvicorn.run(api, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
