import hmac, hashlib
from addons.config import HMAC_SECRET

def sign(data: str):
    return hmac.new(HMAC_SECRET, data.encode(), hashlib.sha256).hexdigest()
