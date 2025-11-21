import base64
import re
import asyncio
import logging
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from config import FORCE_SUB_CHANNEL, ADMINS
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

async def is_subscribed(filter, client, update):
    if not FORCE_SUB_CHANNEL:
        return True
    
    user_id = update.from_user.id
    if user_id in ADMINS:
        return True
    
    try:
        member = await client.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
    except UserNotParticipant:
        return False
    
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
        return False
    else:
        return True

async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = (base64_bytes.decode("ascii")).strip("=")
    return base64_string

async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes)
    string = string_bytes.decode("ascii")
    return string

async def get_messages(client, message_ids):
    """
    FIXED VERSION - Properly handles errors and message retrieval
    """
    messages = []
    total_messages = 0
    
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages:total_messages+200]
        
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=list(temb_ids)
            )
            
            # Filter out None values
            if msgs:
                if isinstance(msgs, list):
                    messages.extend([m for m in msgs if m is not None])
                else:
                    if msgs:  # Single message
                        messages.append(msgs)
            
            logger.info(f"Retrieved {len([m for m in msgs if m is not None])} messages")
            
        except FloodWait as e:
            logger.warning(f"FloodWait: sleeping for {e.x} seconds")
            await asyncio.sleep(e.x)
            
            try:
                msgs = await client.get_messages(
                    chat_id=client.db_channel.id,
                    message_ids=list(temb_ids)
                )
                
                if msgs:
                    if isinstance(msgs, list):
                        messages.extend([m for m in msgs if m is not None])
                    else:
                        if msgs:
                            messages.append(msgs)
                
                logger.info(f"Retrieved {len([m for m in msgs if m is not None])} messages after retry")
                
            except Exception as retry_error:
                logger.error(f"Failed to get messages after FloodWait: {retry_error}")
                # Skip this batch and continue
                
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            logger.error(f"Failed message IDs: {temb_ids}")
            # Don't add to messages - skip this batch
        
        total_messages += len(temb_ids)
    
    logger.info(f"Total messages retrieved: {len(messages)}")
    
    if not messages:
        logger.warning("No messages were retrieved from DB channel!")
    
    return messages

async def get_message_id(client, message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        else:
            return 0
    elif message.forward_sender_name:
        return 0
    elif message.text:
        pattern = "https://t.me/(?:c/)?(.*)/(\\d+)"
        matches = re.match(pattern, message.text)
        if not matches:
            return 0
        
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        
        if channel_id.isdigit():
            if f"-100{channel_id}" == str(client.db_channel.id):
                return msg_id
        else:
            if channel_id == client.db_channel.username:
                return msg_id
        
        return 0
    
    return 0

def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    
    time_list.reverse()
    up_time += ":".join(time_list)
    
    return up_time

subscribed = filters.create(is_subscribed)

# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @Madflix_Bots
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
