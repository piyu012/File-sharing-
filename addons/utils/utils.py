import base64

def encode_payload(text):
    return base64.urlsafe_b64encode(text.encode()).decode()

def decode_payload(text):
    return base64.urlsafe_b64decode(text.encode()).decode()
