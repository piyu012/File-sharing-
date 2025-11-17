import asyncio
from bot import Bot  # अपने bot.py का Bot class

bot = Bot()

# Async-safe run
async def main():
    await bot.start_forever()  # Bot class में start_forever method implement करना होगा

if __name__ == "__main__":
    asyncio.run(main())
