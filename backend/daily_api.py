"""Create a Daily room + an owner token for the bot, via Daily's REST API.
Daily handles all the WebRTC/NAT/TURN, so audio works for anyone on the free tier."""
import os
import time

import httpx

_DAILY_API_KEY = os.getenv("DAILY_API_KEY", "")
_ROOM_TTL_SECONDS = 60 * 30  # rooms auto-expire after 30 min


async def create_room_and_token() -> tuple[str, str]:
    """Returns (room_url, bot_token). The candidate joins the public room with just the URL;
    the bot joins with the owner token."""
    exp = int(time.time()) + _ROOM_TTL_SECONDS
    headers = {"Authorization": f"Bearer {_DAILY_API_KEY}"}
    async with httpx.AsyncClient(timeout=15) as c:
        room_resp = await c.post(
            "https://api.daily.co/v1/rooms",
            headers=headers,
            json={
                "properties": {
                    "exp": exp,
                    "eject_at_room_exp": True,
                    "enable_prejoin_ui": False,
                    "start_video_off": True,
                    "enable_chat": False,
                }
            },
        )
        room_resp.raise_for_status()
        room = room_resp.json()

        token_resp = await c.post(
            "https://api.daily.co/v1/meeting-tokens",
            headers=headers,
            json={"properties": {"room_name": room["name"], "is_owner": True, "exp": exp}},
        )
        token_resp.raise_for_status()
        token = token_resp.json()["token"]

    return room["url"], token
