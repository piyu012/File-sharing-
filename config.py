import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
API_ID = int(os.environ.get("API_ID", "YOUR_API_ID"))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot_username")

# Database
DATABASE_URI = os.environ.get("DATABASE_URI", "mongodb+srv://username:password@cluster.mongodb.net/botdb")
DATABASE_CHANNEL = int(os.environ.get("DATABASE_CHANNEL", "-100123456789"))

# Admin Settings
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "123456789").split()))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@your_admin")

# Force Subscription
FORCE_SUB_CHANNELS = os.environ.get("FORCE_SUB_CHANNELS", "-1001234567890").split()

# Link Shortener
ENABLE_SHORTENER = os.environ.get("ENABLE_SHORTENER", "True").lower() == "true"
SHORTENER_API_URL = os.environ.get("SHORTENER_API_URL", "https://api.short.io/links")
SHORTENER_API_KEY = os.environ.get("SHORTENER_API_KEY", "your_shortener_api_key")

# Ads Configuration
ENABLE_ADS = os.environ.get("ENABLE_ADS", "True").lower() == "true"
AD_LINK = os.environ.get("AD_LINK", "https://your-ad-link.com")
AD_WAIT_TIME = int(os.environ.get("AD_WAIT_TIME", "5"))  # seconds

# Token Settings
DEFAULT_TOKEN_VALIDITY = 30  # days
AUTO_DELETE_EXPIRED = True
