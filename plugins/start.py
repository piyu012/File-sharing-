import os, asyncio, humanize
import time, hmac, hashlib
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, FILE_AUTO_DELETE
from helper_func import subscribed, encode, decode, get_messages
from database.database import add_user, del_user, full_userbase, present_user

# ===================== TOKEN AD SYSTEM IMPORTS ======================
from addons.shortener import gen   # shortener function
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BASE_URL = os.getenv("BASE_URL")
TOKEN_VALIDITY = 18 * 3600  # 18 Hours
# ====================================================================


# ======== SIGN FUNCTION ==========
def sign(data: str):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()
# =================================


# ======== TOKEN VERIFY FUNCTION =========
def verify_token(payload: str, sig: str):
    expected = sign(payload)
    if expected != sig:
        return False

    try:
        uid, ts = payload.split(":")
        ts = int(ts)
    except:
        return False

    if time.time() - ts > TOKEN_VALIDITY:
        return False

    return True
# =========================================


madflixofficials = FILE_AUTO_DELETE
file_auto_delete = humanize.naturaldelta(madflixofficials)



# ================== /START COMMAND ==================
@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):

    uid = message.from_user.id

    # USER REGISTRATION
    if not await present_user(uid):
        try:
            await add_user(uid)
        except:
            pass

    # ============ TOKEN CHECK ================
    if len(message.text.split()) == 1:
        # कोई payload नहीं = normal /start
        return await send_welcome(client, message)

    # /start xxxxxxx (payload)
    arg = message.text.split(" ", 1)[1]

    if "payload=" in arg:
        # ?payload=xxx&sig=xxx से आया user
        return await handle_token_callback(client, message)

    # Old file-sharing code (BASE64 ID SYSTEM)
    return await handle_old_start_system(client, message)



# ================== TOKEN HANDLER ==================
async def handle_token_callback(client, message):
    try:
        query = message.text.split(" ", 1)[1]

        payload = query.split("payload=")[1].split("&")[0]
        sig = query.split("sig=")[1]
    except:
        return await message.reply("Invalid Token ❌")

    if verify_token(payload, sig) is False:
        # TOKEN EXPIRED
        short = gen(f"{BASE_URL}/watch?payload={payload}&sig={sig}")

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("Click Here", url=short)]
        ])

        return await message.reply(
            "❌ <b>Your Ads token is expired</b>\n\n"
            "⏳ <b>Token Timeout:</b> 18 Hours\n\n"
            "Please watch ad again to refresh your token.",
            reply_markup=btn
        )

    # VALID TOKEN — allow bot usage
    return await send_welcome(client, message)



# ================= WELCOME FUNCTION ==================
async def send_welcome(client, message):
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("😊 About Me", callback_data="about"),
                InlineKeyboardButton("🔒 Close", callback_data="close")
            ]
        ]
    )

    return await message.reply_text(
        text=START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )


# ================= OLD FILE SHARING SYSTEM ==================
async def handle_old_start_system(client, message):
    text = message.text
    base64_string = text.split(" ", 1)[1]
    string = await decode(base64_string)
    argument = string.split("-")

    if len(argument) == 3:
        try:
            start = int(int(argument[1]) / abs(client.db_channel.id))
            end = int(int(argument[2]) / abs(client.db_channel.id))
        except:
            return

        if start <= end:
            ids = range(start, end + 1)
        else:
            ids = []
            i = start
            while True:
                ids.append(i)
                i -= 1
                if i < end:
                    break

    elif len(argument) == 2:
        try:
            ids = [int(int(argument[1]) / abs(client.db_channel.id))]
        except:
            return
    else:
        return await send_welcome(client, message)

    temp_msg = await message.reply("Please Wait...")

    try:
        messages = await get_messages(client, ids)
    except:
        return await message.reply_text("Error fetching message!")

    await temp_msg.delete()

    madflix_msgs = []

    for msg in messages:
        caption = msg.caption.html if msg.caption else None

        try:
            madflix_msg = await msg.copy(
                chat_id=message.chat.id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None,
                protect_content=PROTECT_CONTENT
            )
            madflix_msgs.append(madflix_msg)

        except FloodWait as e:
            await asyncio.sleep(e.x)
            madflix_msg = await msg.copy(
                chat_id=message.chat.id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
            madflix_msgs.append(madflix_msg)

    k = await client.send_message(
        chat_id=message.from_user.id,
        text=f"<b>❗️ IMPORTANT ❗️</b>\n\nThis file will be deleted in {file_auto_delete}."
    )

    asyncio.create_task(delete_files(madflix_msgs, client, k))



# ================== /TOKEN COMMAND ==================
@Bot.on_message(filters.command("token") & filters.private)
async def token_cmd(c, m):
    uid = m.from_user.id
    payload = f"{uid}:{int(time.time())}"
    sig = sign(payload)

    raw = f"{BASE_URL}/watch?payload={payload}&sig={sig}"
    try:
        short = gen(raw)
    except:
        short = raw

    await m.reply(
        f"🎁 <b>Ad देखकर Token Claim करें:</b>\n\n👉 {short}",
        parse_mode="html"
    )



# ================ DELETE FILES ==================
async def delete_files(messages, client, k):
    await asyncio.sleep(FILE_AUTO_DELETE)
    for msg in messages:
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=[msg.id])
        except:
            pass

    await k.edit_text("File Deleted Successfully ✔")
