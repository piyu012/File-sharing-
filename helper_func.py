import base64

async def encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()

async def decode(text: str) -> str:
    return base64.urlsafe_b64decode(text.encode()).decode()
