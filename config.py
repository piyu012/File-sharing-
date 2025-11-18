# config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")

MONGO_URI = os.getenv("MONGO_URI")
BOT_USERNAME = os.getenv("BOT_USERNAME")  # without @

HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret")
ADRINO_API = os.getenv("ADRINO_API", "")

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# ===== VERY IMPORTANT =====
# Correct channel ID should be like: -100XXXXXXXXXX
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))

DB_NAME = os.getenv("DB_NAME", "filesharebott")
