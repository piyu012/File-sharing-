import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from addons.database.mongo import tokens_col
from datetime import datetime

router = APIRouter()

@router.get("/watch", response_class=HTMLResponse)
async def watch(data: str):
    try:
        decoded = base64.urlsafe_b64decode(data.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
    except:
        raise HTTPException(400, "Invalid Data")

    doc = await tokens_col.find_one({"payload": payload, "sig": sig})
    if not doc:
        raise HTTPException(404, "Token Not Found")

    now = datetime.utcnow()
    if doc["expires_at"] < now:
        raise HTTPException(403, "Token Expired")

    if doc["used"]:
        raise HTTPException(403, "Token Already Used")

    return f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/callback?data={data}" />
    </head>
    <body>Redirecting…</body>
    </html>
    """
