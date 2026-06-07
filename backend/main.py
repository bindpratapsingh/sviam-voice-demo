"""FastAPI backend for the hosted voice-interview demo.

Public:  POST /sessions, GET /sessions/{id}/scorecard
Admin (password in body):  /admin/verify, /admin/session, /admin/config/get, /admin/config/set
"""
import asyncio
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

load_dotenv()

from uuid import uuid4  # noqa: E402

import bot  # noqa: E402
import config  # noqa: E402
import livekit_token as lk  # noqa: E402
import storage  # noqa: E402

app = FastAPI(title="SViam Voice Interview Demo")

# CORS: allow the Vercel frontend (set FRONTEND_ORIGIN), default open for the demo.
_origin = os.getenv("FRONTEND_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origin == "*" else [_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True}


class CreateSession(BaseModel):
    language: str = "en-US"
    strictness: str = "standard"


@app.post("/sessions")
async def create_session(body: CreateSession):
    cfg = await config.get_config()
    if not cfg.get("deepgram_key"):
        raise HTTPException(400, "No Deepgram key configured (set it in the admin panel).")
    if not (lk.LIVEKIT_URL and lk.API_KEY and lk.API_SECRET):
        raise HTTPException(400, "LiveKit not configured (set LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET).")

    room = f"interview-{uuid4().hex[:10]}"
    bot_token = lk.make_token(room, "aria-bot", "Aria")
    candidate_token = lk.make_token(room, "candidate", "Candidate")
    session_id = await storage.create_session(body.language, body.strictness, room)
    # Run the bot in the background; it joins the same room the candidate is about to join.
    asyncio.create_task(
        bot.run_interview(lk.LIVEKIT_URL, bot_token, room, session_id, body.language, body.strictness, cfg)
    )
    logger.info(f"session {session_id} created ({body.language}/{body.strictness}) room={room}")
    return {"session_id": session_id, "url": lk.LIVEKIT_URL, "token": candidate_token}


@app.get("/sessions/{session_id}/scorecard")
async def get_scorecard(session_id: str):
    sc = await storage.get_scorecard(session_id)
    if not sc:
        return {"status": "pending"}
    return {
        "status": "ready",
        "verdict": sc.get("verdict"),
        "recommendation": sc.get("recommendation"),
        "summary": sc.get("summary"),
    }


# ── Admin (password gated) ──────────────────────────────────────────────────
class AdminAuth(BaseModel):
    password: str


class AdminSession(BaseModel):
    password: str
    session_id: str


class AdminConfigSet(BaseModel):
    password: str
    deepgram_key: str | None = None
    elevenlabs_key: str | None = None
    elevenlabs_voice_id: str | None = None
    groq_key: str | None = None
    anthropic_key: str | None = None
    llm_provider: str | None = None
    tts_provider: str | None = None


async def _check_admin(password: str):
    cfg = await config.get_config()
    if not password or password != cfg.get("admin_password"):
        raise HTTPException(401, "Invalid admin password")


@app.post("/admin/verify")
async def admin_verify(body: AdminAuth):
    await _check_admin(body.password)
    return {"ok": True}


@app.post("/admin/session")
async def admin_session(body: AdminSession):
    await _check_admin(body.password)
    return await storage.get_session_full(body.session_id)


def _mask(v: str | None) -> str:
    if not v:
        return ""
    return f"…{v[-4:]}" if len(v) > 4 else "set"


@app.post("/admin/config/get")
async def admin_config_get(body: AdminAuth):
    await _check_admin(body.password)
    cfg = await config.get_config()
    # Mask secrets; expose providers/voice for the editor.
    return {
        "deepgram_key": _mask(cfg.get("deepgram_key")),
        "elevenlabs_key": _mask(cfg.get("elevenlabs_key")),
        "groq_key": _mask(cfg.get("groq_key")),
        "anthropic_key": _mask(cfg.get("anthropic_key")),
        "elevenlabs_voice_id": cfg.get("elevenlabs_voice_id"),
        "llm_provider": cfg.get("llm_provider"),
        "tts_provider": cfg.get("tts_provider"),
    }


@app.post("/admin/config/set")
async def admin_config_set(body: AdminConfigSet):
    await _check_admin(body.password)
    updates = body.model_dump(exclude={"password"}, exclude_none=True)
    await config.update_config(updates)
    return {"ok": True}
