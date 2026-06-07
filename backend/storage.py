"""Supabase persistence via its REST (PostgREST) API — no extra SDK, just httpx.
Tables: sessions, turns, scorecards (see ../supabase/schema.sql)."""
import os

import httpx

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _h(extra: dict | None = None):
    h = {
        "apikey": _KEY,
        "Authorization": f"Bearer {_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


async def create_session(language: str, strictness: str, daily_room: str) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{_URL}/rest/v1/sessions",
            json={
                "language": language,
                "strictness": strictness,
                "daily_room": daily_room,
                "status": "live",
            },
            headers=_h({"Prefer": "return=representation"}),
        )
    r.raise_for_status()
    return r.json()[0]["id"]


async def save_turns(session_id: str, transcript: list[dict]) -> None:
    if not transcript:
        return
    rows = [
        {"session_id": session_id, "idx": i, "role": t["role"], "content": t["content"]}
        for i, t in enumerate(transcript)
    ]
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(f"{_URL}/rest/v1/turns", json=rows, headers=_h())


async def save_scorecard(session_id: str, sc: dict, signals: dict) -> None:
    row = {
        "session_id": session_id,
        "verdict": sc.get("verdict"),
        "recommendation": sc.get("recommendation"),
        "summary": sc.get("summary"),
        "strengths": sc.get("strengths", []),
        "areas_to_improve": sc.get("areas_to_improve", []),
        "communication": sc.get("communication"),
        "signals": signals or {},
    }
    async with httpx.AsyncClient(timeout=15) as c:
        await c.post(
            f"{_URL}/rest/v1/scorecards",
            json=row,
            headers=_h({"Prefer": "resolution=merge-duplicates"}),
        )


async def set_session_status(session_id: str, status: str) -> None:
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(
            f"{_URL}/rest/v1/sessions",
            params={"id": f"eq.{session_id}"},
            json={"status": status},
            headers=_h(),
        )


async def get_scorecard(session_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{_URL}/rest/v1/scorecards",
            params={"session_id": f"eq.{session_id}", "select": "*"},
            headers=_h(),
        )
    rows = r.json() if r.status_code == 200 else []
    return rows[0] if rows else None


async def get_session_full(session_id: str) -> dict:
    """Everything for the admin reasoning view: session + transcript + scorecard."""
    async with httpx.AsyncClient(timeout=12) as c:
        s = await c.get(
            f"{_URL}/rest/v1/sessions",
            params={"id": f"eq.{session_id}", "select": "*"},
            headers=_h(),
        )
        t = await c.get(
            f"{_URL}/rest/v1/turns",
            params={"session_id": f"eq.{session_id}", "select": "role,content,idx", "order": "idx"},
            headers=_h(),
        )
    sc = await get_scorecard(session_id)
    return {
        "session": (s.json() or [None])[0] if s.status_code == 200 else None,
        "turns": t.json() if t.status_code == 200 else [],
        "scorecard": sc,
    }
