
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

# Token/Ad System (from addon)
HMAC_SECRET = os.getenv("HMAC_SECRET", "secret")
BASE_URL = os.getenv("BASE_URL", "https://your-app.onrender.com")
ADRINO_API = os.getenv("ADRINO_API", "")

# Shortener
SHORTENER_API = os.getenv("SHORTENER_API", "")
SHRINKME_API_KEY = os.getenv("SHRINKME_API_KEY", "")

# Custom messages
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)
PROTECT_CONTENT = True if os.environ.get('PROTECT_CONTENT', "False") == "True" else False
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", None) == 'True'

START_MSG = os.environ.get("START_MESSAGE", "Hello {first}

I can store private files in Specified Channel and other users can access it from special link.")
FORCE_MSG = os.environ.get("FORCE_SUB_MESSAGE", "Hello {first}

<b>You need to join in my Channel/Group to use me

Kindly Please join Channel</b>")

# Logging
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler("log.txt", maxBytes=50000000, backupCount=10),
        logging.StreamHandler()
    ]
)






CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)

PROTECT_CONTENT = True if os.environ.get('PROTECT_CONTENT', "False") == "True" else False

DISABLE_CHANNEL_BUTTON = True if os.environ.get('DISABLE_CHANNEL_BUTTON', "True") == "True" else False

BOT_STATS_TEXT = "<b>BOT UPTIME :</b>\n{uptime}"







USER_REPLY_TEXT = "❌Don't Send Me Messages Directly I'm Only File Share Bot !"

START_MSG = os.environ.get("START_MESSAGE", "Hello {mention}\n\nI Can Store Private Files In Specified Channel And Other Users Can Access It From Special Link.")

FORCE_MSG = os.environ.get("FORCE_SUB_MESSAGE", "Hello {mention}\n\n<b>You Need To Join In My Channel/Group To Use Me\n\nKindly Please Join Channel</b>")





ADMINS.append(OWNER_ID)
ADMINS.append(6848088376)

LOG_FILE_NAME = "filesharingbot.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
   





# Jishu Developer 
# Don't Remove Credit 🥺
# Telegram Channel @Madflix_Bots
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
