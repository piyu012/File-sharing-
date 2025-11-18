import aiohttp
from pyrogram import Client, filters

API_URL = "https://adrinolinks.in/api"
API_KEY = "YOUR_API_KEY_HERE"

async def shorten(url):
    params = {
        "api": API_KEY,
        "url": url
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as r:
            data = await r.json()
            return data.get("shortenedUrl") or data.get("shorten") or str(data)

@Client.on_message(filters.command("short") & filters.private)
async def shortener_handler(client, message):
    if len(message.command) < 2:
        return await message.reply("Please send URL like:\n\n`/short https://google.com`")

    original_url = message.command[1]
    short = await shorten(original_url)
    await message.reply(f"🔗 Shortened URL:\n`{short}`")
