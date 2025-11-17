import requests, os

API = os.getenv("SHORTENER_API")

def gen(url):
    try:
        r = requests.get("https://shrinkme.io/api", params={
            "api_key": API,
            "format": "json",
            "url": url
        })
        return r.json().get("shortenedUrl", url)
    except:
        return url
