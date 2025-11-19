from pyrogram import Client, filters
from addons.utils import decode_payload
from addons.db import files_col

@Client.on_message(filters.command("start"))
async def start(bot, message):
    args = message.text.split()

    # no deep link → show welcome message
    if len(args) == 1:
        await message.reply_text("👋 Welcome! Send /help")
        return

    # deep-link found
    encoded = args[1]

    try:
        payload = decode_payload(encoded)  
    except:
        await message.reply_text("❌ Invalid link.")
        return

    # check if payload is file request
    if payload.startswith("get-"):
        file_doc = await files_col.find_one({"payload": payload})

        if not file_doc:
            await message.reply_text("❌ File not found.")
            return

        file_id = file_doc["file_id"]
        ftype = file_doc["file_type"]

        # send file back
        if ftype == "video":
            await bot.send_video(message.chat.id, file_id)
        elif ftype == "document":
            await bot.send_document(message.chat.id, file_id)
        elif ftype == "audio":
            await bot.send_audio(message.chat.id, file_id)
        elif ftype == "photo":
            await bot.send_photo(message.chat.id, file_id)

        return

    # otherwise → normal start
    await message.reply_text("👋 Welcome!")
