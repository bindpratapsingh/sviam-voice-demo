"""Generate LiveKit access tokens (HS256 JWT). No server SDK — just PyJWT.
LiveKit Cloud's free tier needs no credit card and relays the media for us."""
import os
import time

import jwt

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
API_KEY = os.getenv("LIVEKIT_API_KEY", "")
API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


def make_token(room: str, identity: str, name: str = "", ttl: int = 1800) -> str:
    now = int(time.time())
    claims = {
        "iss": API_KEY,
        "sub": identity,
        "name": name or identity,
        "nbf": now,
        "iat": now,
        "exp": now + ttl,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    return jwt.encode(claims, API_SECRET, algorithm="HS256")
