import os, hmac, hashlib, time, asyncio, requests, urllib.parse
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pyrogram import Client, filters

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADRINO_API = os.getenv("ADRINO_API")   # Put your Adrinolinks API KEY in Render env

api = FastAPI()

# ---------------- Pyrogram Client ----------------
bot = Client(
    "adbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---------------- HMAC SIGN ----------------
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

# ---------------- ADRINOLINKS SHORTENER ----------------
def short_adrinolinks(long_url):
    try:
        api_url = f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        r = requests.get(api_url).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

# ---------------- BOT START / STOP ----------------
@api.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# ---------------- BOT HANDLER ----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    ts = int(time.time())

    payload = f"{uid}:{ts}"
    sig = sign(payload)

    # ====== URL-safe encoding ======
    encoded_payload = urllib.parse.quote(payload)

    long_link = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/watch?payload={encoded_payload}&sig={sig}"

    # --------- SHORTEN USING ADRINOLINKS ----------
    short_url = short_adrinolinks(long_link)

    await message.reply_text(
        f"👋 Welcome!\n\n👉 Your short ad link:\n\n{short_url}"
    )

# ---------------- WATCH PAGE ----------------
@api.get("/watch", response_class=HTMLResponse)
async def watch(payload: str, sig: str):
    # Decode payload
    payload = urllib.parse.unquote(payload)

    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    return f"""
    <html>
    <body>
      <h2>Watch Ad</h2>
      <p>Wait 6 seconds…</p>

      <script>
      setTimeout(function(){{
          window.location.href="/callback?payload={payload}&sig={sig}";
      }},6000);
      </script>
    </body>
    </html>
    """

# ---------------- CALLBACK ----------------
@api.get("/callback")
async def callback(payload: str, sig: str):
    # Decode payload
    payload = urllib.parse.unquote(payload)

    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
