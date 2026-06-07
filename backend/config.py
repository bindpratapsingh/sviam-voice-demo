"""Runtime config. The Supabase `app_config` row (id=1) OVERRIDES env vars, so the admin
panel can change API keys live without redeploying. Falls back to env on any missing field."""
import os

import httpx

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Fields the admin panel can edit + their env fallbacks.
_DEFAULTS = {
    "deepgram_key": os.getenv("DEEPGRAM_API_KEY", ""),
    "elevenlabs_key": os.getenv("ELEVENLABS_API_KEY", ""),
    "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "XrExE9yKIg1WjnnlVkGX"),
    "groq_key": os.getenv("GROQ_API_KEY", ""),
    "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),
    "llm_provider": os.getenv("LLM_PROVIDER", "groq"),
    "tts_provider": os.getenv("TTS_PROVIDER", "elevenlabs"),
    "admin_password": os.getenv("ADMIN_PASSWORD", "changeme"),
}


def _headers():
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def get_config() -> dict:
    """Return effective config: Supabase row over env defaults."""
    cfg = dict(_DEFAULTS)
    if not (_SUPABASE_URL and _SUPABASE_KEY):
        return cfg
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/app_config",
                params={"id": "eq.1", "select": "*"},
                headers=_headers(),
            )
        if r.status_code == 200 and r.json():
            row = r.json()[0]
            for k in cfg:
                if row.get(k):
                    cfg[k] = row[k]
    except Exception:  # noqa: BLE001  (never block a session on config read)
        pass
    return cfg


async def update_config(updates: dict) -> None:
    """Patch the singleton app_config row (admin key editor)."""
    if not (_SUPABASE_URL and _SUPABASE_KEY):
        return
    payload = {k: v for k, v in updates.items() if k in _DEFAULTS and v not in (None, "")}
    if not payload:
        return
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(
            f"{_SUPABASE_URL}/rest/v1/app_config",
            params={"id": "eq.1"},
            json=payload,
            headers=_headers(),
        )
