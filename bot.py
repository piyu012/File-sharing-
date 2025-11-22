from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import hashlib
import config

# Initialize bot
app = Client(
    "video_sharing_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Database setup
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS videos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT UNIQUE NOT NULL,
                  unique_code TEXT UNIQUE NOT NULL,
                  caption TEXT,
                  added_by INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Generate unique code
def generate_code(file_id):
    hash_object = hashlib.md5(file_id.encode())
    return hash_object.hexdigest()[:8]

# Save video to database
def save_video(file_id, caption, user_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    unique_code = generate_code(file_id)
    try:
        c.execute("INSERT INTO videos (file_id, unique_code, caption, added_by) VALUES (?, ?, ?, ?)",
                  (file_id, unique_code, caption, user_id))
        conn.commit()
        conn.close()
        return unique_code
    except sqlite3.IntegrityError:
        conn.close()
        return unique_code

# Get video by code
def get_video(code):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT file_id, caption FROM videos WHERE unique_code=?", (code,))
    result = c.fetchone()
    conn.close()
    return result

# Start command
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    # Check if user clicked on a video link
    if len(message.text.split()) > 1:
        code = message.text.split()[1]
        video_data = get_video(code)
        
        if video_data:
            file_id, caption = video_data
            try:
                await message.reply_video(
                    video=file_id,
                    caption=caption if caption else "🎥 यहाँ आपका video है!"
                )
                return
            except Exception as e:
                await message.reply_text(f"❌ Error: {str(e)}")
                return
        else:
            await message.reply_text("⚠️ यह link expired या invalid है!")
            return
    
    # Normal start message
    if message.from_user.id == config.ADMIN_USER_ID:
        await message.reply_text(
            f"👋 Welcome Admin!\n\n"
            f"📤 मुझे कोई video भेजें और मैं उसका shareable link बना दूंगा।\n\n"
            f"📊 Commands:\n"
            f"/start - Start bot\n"
            f"/stats - Video statistics देखें"
        )
    else:
        await message.reply_text(
            "👋 Welcome!\n\n"
            "🎥 इस bot से आप videos access कर सकते हैं।\n"
            "Link पर click करें और video प्राप्त करें!"
        )

# Handle video from admin
@app.on_message(filters.video & filters.private)
async def handle_video(client, message: Message):
    # Check if user is admin
    if message.from_user.id != config.ADMIN_USER_ID:
        await message.reply_text("⛔ आप video upload नहीं कर सकते। केवल admin के लिए।")
        return
    
    # Get video file_id
    file_id = message.video.file_id
    caption = message.caption
    
    # Save to database
    code = save_video(file_id, caption, message.from_user.id)
    
    # Generate shareable link
    share_link = f"{config.BASE_URL}{code}"
    
    # Create inline button
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Link Copy करें", url=share_link)]
    ])
    
    await message.reply_text(
        f"✅ Video successfully uploaded!\n\n"
        f"🔗 **Shareable Link:**\n"
        f"`{share_link}`\n\n"
        f"📋 Code: `{code}`\n\n"
        f"इस link को किसी के साथ भी share कर सकते हैं!",
        reply_markup=keyboard
    )

# Stats command for admin
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message: Message):
    if message.from_user.id != config.ADMIN_USER_ID:
        await message.reply_text("⛔ यह command केवल admin के लिए है।")
        return
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM videos")
    total_videos = c.fetchone()[0]
    conn.close()
    
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"📹 Total Videos: {total_videos}\n"
        f"👤 Admin: You\n"
        f"✅ Bot Status: Active"
    )

# Run bot
print("🤖 Bot starting...")
app.run()
print("✅ Bot is running!")
