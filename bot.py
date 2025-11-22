import os
import asyncio
from aiohttp import web
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram import idle

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", "10000"))
MONGO_URL = os.getenv("MONGO_URL")

# ---------------- DB ----------------
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["shivaadb"]
files_col = db["files"]

# ---------------- BOT ----------------
bot = Client(
    "ShivaaBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
)

# ============================================================
# SAVE FILES + GENERATE LINK
# ============================================================
@bot.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def save_file_handler(client: Client, msg: Message):
    file = msg.video or msg.document or msg.audio
    file_id = file.file_id
    unique_id = file.file_unique_id

    await files_col.update_one(
        {"file_uid": unique_id},
        {"$set": {
            "file_id": file_id,
            "added": datetime.utcnow()
        }},
        upsert=True
    )

    direct_link = f"https://{os.getenv('RENDER_EXTERNAL_URL', 'localhost')}?id={unique_id}"
    await msg.reply(f"**Your File Link:**\n{direct_link}")

# ============================================================
# HTTP SERVER
# ============================================================
async def serve_file(request):
    file_uid = request.query.get("id")
    if not file_uid:
        return web.Response(text="Missing ?id=", status=400)

    data = await files_col.find_one({"file_uid": file_uid})
    if not data:
        return web.Response(text="File not found", status=404)

    file_id = data["file_id"]
    return web.Response(text=f"Use this file_id in Telegram: {file_id}", status=200)


async def start_http_server():
    app = web.Application()
    app.add_routes([web.get("/", serve_file)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"HTTP Server Running on port {PORT}")

# ============================================================
# CLEANUP TASK
# ============================================================
async def cleanup_task():
    while True:
        limit = datetime.utcnow() - timedelta(days=3)
        await files_col.delete_many({"added": {"$lt": limit}})
        await asyncio.sleep(3600)

# ============================================================
# MAIN
# ============================================================
async def main():
    print("Starting HTTP and Cleanup tasks...")
    asyncio.create_task(start_http_server())
    asyncio.create_task(cleanup_task())

    print("Bot fully started!")
    await bot.start()
    await idle()

# ============================================================
# BOOT
# ============================================================
if __name__ == "__main__":
    asyncio.run(main())
