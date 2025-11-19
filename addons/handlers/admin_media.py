from pyrogram import Client, filters
from datetime import datetime
from utils import encode_payload
from addons.db import files_col
import os

ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")

@Client.on_message(filters.user(ADMIN_ID) & (filters.video | filters.document | filters.audio | filters.photo))
async def save_media(bot, message):

    # identify file
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.photo:
        file_id = message.photo.file_id
        file_type = "photo"

    # create unique payload
    payload = f"get-{int(datetime.utcnow().timestamp())}"

    await files_col.insert_one({
        "file_id": file_id,
        "file_type": file_type,
        "owner": ADMIN_ID,
        "payload": payload,
        "created_at": datetime.utcnow()
    })

    encoded = encode_payload(payload)

    link = f"https://t.me/{BOT_USERNAME}?start={encoded}"

    await message.reply_text(
        f"✅ File saved!\n🔗 Share Link:\n{link}"
    )
