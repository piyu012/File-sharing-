from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import bot  # 'bot' instance
from config import ADMIN_ID  # single admin or list of admins
import base64
import asyncio

# ---------------- Helper function ----------------
async def encode(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode()).decode()

# If ADMIN_ID is single integer, wrap in list
ADMINS = [ADMIN_ID] if isinstance(ADMIN_ID, int) else ADMIN_ID
DISABLE_CHANNEL_BUTTON = False  # set True if you don't want buttons in DB channel

# ---------------- ADMIN ONLY FILE/PHOTO/VIDEO LINK GENERATOR ----------------
@bot.on_message(
    filters.private
    & filters.user(ADMINS)
    & (filters.document | filters.photo | filters.video)
)
async def file_link_generator(client: Client, message: Message):
    reply_text = await message.reply_text("⏳ Please wait, generating link...", quote=True)

    if not getattr(client, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        return

    try:
        # Forward the media to DB channel
        post_message = await message.copy(
            chat_id=client.db_channel.id,
            disable_notification=True
        )
    except asyncio.exceptions.TimeoutError:
        await reply_text.edit_text("⚠️ Timeout occurred while forwarding!")
        return
    except Exception as e:
        await reply_text.edit_text(f"❌ Something went wrong: {e}")
        return

    # Generate unique deep link
    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"

    # Create share button
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]]
    )

    # Send link to admin
    await reply_text.edit_text(
        f"<b>Here is your link</b>:\n\n{link}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    # Optionally edit DB channel post with the same button
    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except Exception as e:
            print("Edit Reply Markup Failed:", e)
