import os, aiohttp, urllib.parse
SHRINKME_API_KEY = os.getenv("SHRINKME_API_KEY")
API_ENDPOINT = "https://shrinkme.io/api"

async def shrinkme_shorten(long_url: str) -> str:
    if not SHRINKME_API_KEY:
        return long_url
    params = {"api": SHRINKME_API_KEY, "url": long_url}
    url = f"{API_ENDPOINT}?{urllib.parse.urlencode(params)}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=20) as r:
            data = await r.json(content_type=None)
            return data.get("shortenedUrl") or data.get("short") or long_url
