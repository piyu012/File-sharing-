import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from addons.database.mongo import tokens_col
from datetime import datetime, timedelta
from addons.config import ADMIN_ID, BOT_USERNAME
from addons.bot import bot

router = APIRouter()

@router.get("/callback")
async def callback(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid Data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token not found")

    now = datetime.utcnow()

    if doc["expires_at"] < now:
        raise HTTPException(403, "Token expired")

    if doc["used"]:
        raise HTTPException(403, "Token already used")

    uid, ts = payload.split(":")

    new_expiry = now + timedelta(hours=12)

    await tokens_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "activated_at": now, "expires_at": new_expiry}}
    )

    try:
        await bot.send_message(ADMIN_ID, f"🔔 Token activated by {uid}")
    except:
        pass

    await bot.send_message(
        int(uid),
        f"✅ आपका token verify हो गया!\n⏳ Valid for: 12 Hour"
    )

    deep_link = f"tg://resolve?domain={BOT_USERNAME}&start=done"

    return HTMLResponse(f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url={deep_link}" />
    </head>
    <body>Redirecting…</body>
    </html>
    """)
