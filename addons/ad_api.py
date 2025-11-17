import os, hmac, hashlib, time, asyncio, requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from bot import Bot

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
ADRINO_API = os.getenv("ADRINO_API")

api = FastAPI()
bot = Bot()  # Pyrogram client instance

# SIGN function
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

# URL shortener
def short_adrinolinks(long_url):
    try:
        api_url = f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        r = requests.get(api_url).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

# Startup / Shutdown events
@api.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.start())  # bot background

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# TG /ad command
@bot.on_message()
async def start_cmd(client, message):
    if message.text != "/ad":
        return

    uid = message.from_user.id
    ts = int(time.time())
    payload = f"{uid}:{ts}"
    sig = sign(payload)

    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    long_link = f"https://{hostname}/watch?payload={payload}&sig={sig}"
    short_url = short_adrinolinks(long_link)

    await message.reply_text(f"👉 Your Ad Link:\n{short_url}")

# /watch endpoint
@api.get("/watch", response_class=HTMLResponse)
async def watch(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    return f"""
    <html>
    <body>
        <h2>Watch Ad</h2>
        <p>Wait 6 seconds…</p>
        <script>
        setTimeout(function() {{
            window.location.href="/callback?payload={payload}&sig={sig}";
        }}, 6000);
        </script>
    </body>
    </html>
    """

# /callback endpoint
@api.get("/callback")
async def callback(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    uid, ts = payload.split(":")
    token = str(int(time.time()))
    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
