import os

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

ADRINO_API = os.getenv("ADRINO_API")
MONGO_URI = os.getenv("MONGO_URI")

DB_NAME = "filesharebott"
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")

HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")
