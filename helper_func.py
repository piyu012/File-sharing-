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
    
    return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]

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
    messages = []
    total_messages = 0
    
    while total_messages != len(message_ids):
        temp_ids = message_ids[total_messages:total_messages+200]
        
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=list(temp_ids)
            )
            
            if msgs:
                if isinstance(msgs, list):
                    messages.extend([m for m in msgs if m is not None])
                else:
                    if msgs:
                        messages.append(msgs)
            
            logger.info(f"Retrieved {len([m for m in msgs if m is not None])} messages")
            
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value}s")
            await asyncio.sleep(e.value)
            
            try:
                msgs = await client.get_messages(
                    chat_id=client.db_channel.id,
                    message_ids=list(temp_ids)
                )
                
                if msgs:
                    if isinstance(msgs, list):
                        messages.extend([m for m in msgs if m is not None])
                    else:
                        if msgs:
                            messages.append(msgs)
                            
            except Exception as retry_error:
                logger.error(f"Retry failed: {retry_error}")
                
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
        
        total_messages += len(temp_ids)
    
    logger.info(f"Total messages retrieved: {len(messages)}")
    return messages

subscribed = filters.create(is_subscribed)
