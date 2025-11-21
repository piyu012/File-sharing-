import os
import logging
from logging.handlers import RotatingFileHandler

# Bot credentials
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
OWNER_ID = int(os.environ.get("OWNER_ID", ""))

# Database
DB_URL = os.environ.get("DB_URL", "")
DB_NAME = os.environ.get("DB_NAME", "filesharebott")

# Channels
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", ""))
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "0"))

# File settings
FILE_AUTO_DELETE = int(os.getenv("FILE_AUTO_DELETE", "600"))

# Server
PORT = os.environ.get("PORT", "8080")
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))

# Admins
try:
    ADMINS = [OWNER_ID]
    for x in (os.environ.get("ADMINS", str(OWNER_ID)).split()):
        ADMINS.append(int(x))
except ValueError:
    raise Exception("Your Admins list does not contain valid integers.")

# Ad System
HMAC_SECRET = os.getenv("HMAC_SECRET", "your_secret_key_here")
BASE_URL = os.getenv("BASE_URL", "https://your-app.onrender.com")
ADRINO_API = os.getenv("ADRINO_API", None)

# Messages
START_MSG = os.environ.get("START_MESSAGE", "Hello {first}

I can store files and give you shareable links!")

CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)

# Buttons
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", None) == 'True'
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False") == 'True'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler("log.txt", maxBytes=50000000, backupCount=10),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)
