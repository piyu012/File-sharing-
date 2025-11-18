# config.py
import os

# Required
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
MONGO_URI = os.getenv("MONGO_URI", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # without @
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")

# Optional / defaults
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret")
ADRINO_API = os.getenv("ADRINO_API", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # single admin id
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # -100... channel id required for posting
DB_NAME = os.getenv("DB_NAME", "filesharebott")
