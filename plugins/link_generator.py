from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS
from helper_func import encode, get_message_id


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    while True:
        try:
            first_message = await client.ask(
                text="Forward The First Message From DB Channel (With Quotes)..\n\nOr Send The DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return

        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("❌ Error\n\nThis Forwarded Post Is Not From DB Channel", quote=True)

    while True:
        try:
            second_message = await client.ask(
                text="Forward The Last Message From DB Channel (With Quotes)..\n\nOr Send The DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return

        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("❌ Error\n\nThis Forwarded Post Is Not From DB Channel", quote=True)

    # FIXED — No multiplication
    string = f"get-{f_msg_id}-{s_msg_id}"
    base64_string = await encode(string)

    link = f"https://t.me/{client.username}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]
    ])

    await second_message.reply_text(f"<b>Here Is Your Link</b>\n\n{link}", reply_markup=reply_markup, quote=True)



@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):

    while True:
        try:
            channel_message = await client.ask(
                text="Forward Message From DB Channel (With Quotes)..\n\nOr Send DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return

        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("❌ Not from DB channel!", quote=True)

    # FIXED — No multiplication
    base64_string = await encode(f"get-{msg_id}")
    link = f"https://t.me/{client.username}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]
    ])

    await channel_message.reply_text(f"<b>Here Is Your Link</b>\n\n{link}", reply_markup=reply_markup, quote=True)
