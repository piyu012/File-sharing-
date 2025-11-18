import requests
from config import ADRINO_API

def short_adrinolinks(long_url):
    try:
        r = requests.get(
            f"https://adrinolinks.in/api?api={ADRINO_API}&url={long_url}"
        ).json()
        return r.get("shortenedUrl", long_url)
    except:
        return long_url
