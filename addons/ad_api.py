import os, hmac, hashlib, time, asyncio, requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from bot import Bot  # <-- USE YOUR OLD BOT HERE

HMAC_SECRET = os.getenv("HMAC_SECRET", "secret").encode()
ADRINO_API = os.getenv("ADRINO_API")

# ------- FASTAPI -------
api = FastAPI()

# ------- USE OLD BOT CLIENT -------
bot = Bot()  # <-- Pyrogram Client instance only
# DO NOT start internal web server in bot.py to avoid port conflict

# ------- SIGN -------
def sign(data):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()

# ------- SHORTENER -------
def short_adrinolinks(long_url):
    try:
        api_url = f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        r = requests.get(api_url).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url

# ------- START / STOP -------
@api.on_event("startup")
async def startup_event():
    # Bot start in background
    asyncio.create_task(bot.start())

@api.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# ------- TG /ad command -------
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

# ------- WATCH -------
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

# ------- CALLBACK -------
@api.get("/callback")
async def callback(payload: str, sig: str):
    if not hmac.compare_digest(sign(payload), sig):
        raise HTTPException(401, "Invalid Signature")

    uid, ts = payload.split(":")
    token = str(int(time.time()))

    await bot.send_message(int(uid), f"🎉 Your Token:\n\n`{token}`")

    return {"ok": True, "token": token}
