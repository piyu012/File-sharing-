from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import bot, ADMINS
import base64
import asyncio

# ---------------- ADMIN ONLY FILE/PHOTO/VIDEO LINK GENERATOR ----------------
@bot.on_message(
    filters.private
    & filters.user(ADMINS)
    & (filters.document | filters.photo | filters.video)
)
async def file_link_generator(client: Client, message: Message):
    print("File handler triggered", message.from_user.id)  # Logging

    reply_text = await message.reply_text("⏳ Please wait, generating link...", quote=True)

    if not getattr(client, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        return

    try:
        # Forward the media to DB channel
        post_message = await message.copy(
            chat_id=client.db_channel,
            disable_notification=True
        )
    except asyncio.exceptions.TimeoutError:
        await reply_text.edit_text("⚠️ Timeout occurred while forwarding!")
        return
    except Exception as e:
        await reply_text.edit_text(f"❌ Something went wrong: {e}")
        return

    # Generate unique deep link
    converted_id = post_message.id * abs(client.db_channel)
    string = f"get-{converted_id}"
    base64_string = base64.urlsafe_b64encode(string.encode()).decode()
    link = f"https://t.me/{BOT_USERNAME}?start={base64_string}"

    # Create share button
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]]
    )

    # Send link to admin
    await reply_text.edit(
        f"<b>Here is your link</b>:\n\n{link}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
