# helper_func.py
import base64

async def encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()

async def decode(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode()).decode()
