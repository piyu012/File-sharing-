import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from bot import Bot
from config import ADMINS, DISABLE_CHANNEL_BUTTON
from helper_func import encode
import traceback

@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(
    ['start','users','broadcast','batch','genlink','stats']))
async def channel_post(client: Client, message: Message):
    # quick reply so user sees bot is working
    reply_text = await message.reply_text("Please Wait...!", quote=True)

    # 1) db_channel check
    if not getattr(client, "db_channel", None):
        await reply_text.edit_text("⚠️ Database Channel not set!")
        return

    # 2) quick permission check (try a harmless action)
    try:
        # try to get channel id to ensure it's valid and bot has access
        _ = client.db_channel.id
    except Exception as e:
        await reply_text.edit_text("⚠️ Invalid channel config.")
        return

    # 3) Attempt to copy - with FloodWait handling
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)

    except FloodWait as e:
        # wait and retry once
        await asyncio.sleep(e.x)
        try:
            post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
        except Exception as e2:
            err_text = f"Copy failed after FloodWait: {e2.__class__.__name__}: {str(e2)[:250]}"
            await _report_and_reply(client, reply_text, err_text, e2)
            return

    except Exception as e:
        err_text = f"Copy failed: {e.__class__.__name__}: {str(e)[:250]}"
        await _report_and_reply(client, reply_text, err_text, e)
        return

    # 4) Create link and edit/reply
    try:
        converted_id = post_message.id * abs(client.db_channel.id)
        string = f"get-{converted_id}"
        base64_string = await encode(string)
        link = f"https://t.me/{client.username}?start={base64_string}"

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]]
        )

        try:
            await reply_text.edit(
                "<b>Here Is Your Link</b>\n\n" + link,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except MessageNotModified:
            pass

        if not DISABLE_CHANNEL_BUTTON:
            try:
                await post_message.edit_reply_markup(reply_markup)
            except Exception as e:
                # Not fatal, log and continue
                print("Edit Reply Markup Failed:", e)

    except Exception as e:
        err_text = f"Post/edit failed: {e.__class__.__name__}: {str(e)[:250]}"
        await _report_and_reply(client, reply_text, err_text, e)
        return


# helper to report error to admin and edit user's message with friendly hint
async def _report_and_reply(client: Client, reply_obj, short_err: str, exc: Exception):
    # print full traceback to server logs
    print("---- channel_post error ----")
    traceback.print_exc()

    # try send detailed error to first admin (if available)
    try:
        admin_id = ADMINS[0] if isinstance(ADMINS, (list, tuple)) and len(ADMINS) > 0 else None
        if admin_id:
            # send concise error to admin (avoid huge trace in message)
            await client.send_message(admin_id, f"Channel post error: {short_err}")
    except Exception as e:
        print("Failed sending error to admin:", e)

    # friendly reply to user
    try:
        await reply_obj.edit_text("Something Went Wrong..! (Admin notified)\nTry sending plain text first.")
    except MessageNotModified:
        pass
