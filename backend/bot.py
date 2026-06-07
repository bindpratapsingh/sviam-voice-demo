"""The Pipecat voice-interview pipeline for the hosted demo.

Per session: Daily transport (audio) → Deepgram (Flux for en/hi, Nova-3 for te/ta) →
dynamics → LLM (keys from live config) → ElevenLabs TTS → Daily. On the candidate leaving,
it writes the transcript + a fair scorecard to Supabase.
"""
import os

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport

import storage
from core.language_config import get_language_config
from core.strictness_profiles import compose_system_prompt, get_strictness_profile
from processors.dynamics import Dynamics
from processors.latency import LatencyLogger
from scorecard import generate_scorecard

SYSTEM_PROMPT = (
    "You are Aria, a warm but sharp technical interviewer in a live VOICE interview. "
    "Speak naturally and concisely — one or two sentences per turn, like a real conversation. "
    "Ask ONE question at a time. Never read long lists aloud. "
    "You ASK and PROBE — you do NOT answer technical questions for the candidate. "
    "If they ask you to define, explain, compare, or say 'you tell me first', do NOT give the answer: "
    "warmly turn it back, e.g. 'I'd like to hear how YOU would explain it.' "
    "At most offer a one-line hint to unstick them — never the full answer. "
    "Probe their reasoning: ask why, and gently push on vague answers. "
    "Stay in your interviewer role; if challenged about it, acknowledge briefly and steer back. "
    "If the candidate asks for time, a moment, or says they need to think — in ANY language — "
    "briefly acknowledge (e.g. 'Of course, take your time') and then STOP. Do NOT ask anything new "
    "or keep talking until they speak again. "
    "Keep technical terms in English. Be encouraging but substantive."
)

_DEFAULT_GREETING = (
    "Hi, I'm Aria, your interviewer today. Thanks for joining. "
    "To get us started, tell me a bit about yourself."
)
_GREETINGS = {
    "hi-IN": "नमस्ते, मैं आरिया हूँ — आज आपका इंटरव्यू मैं लूँगी। शामिल होने के लिए धन्यवाद। "
    "चलिए शुरू करते हैं, अपने बारे में थोड़ा बताइए।",
    "te-IN": "నమస్కారం, నేను ఆరియా — ఈరోజు మీ ఇంటర్వ్యూ నేను చేస్తాను. చేరినందుకు ధన్యవాదాలు. "
    "మీ గురించి కొంచెం చెప్పండి.",
    "ta-IN": "வணக்கம், நான் ஆரியா — இன்று உங்கள் நேர்காணலை நான் நடத்துகிறேன். இணைந்ததற்கு நன்றி. "
    "உங்களைப் பற்றி கொஞ்சம் சொல்லுங்கள்.",
}
_STRICTNESS_NAMES = {"friendly": 1, "standard": 2, "tough": 3, "adversarial": 4}


def _resolve_strictness(value: str) -> int:
    v = (value or "").strip().lower()
    if v in _STRICTNESS_NAMES:
        return _STRICTNESS_NAMES[v]
    try:
        return int(v)
    except (TypeError, ValueError):
        return 2


def _make_llm(system_prompt: str, cfg: dict):
    provider = (cfg.get("llm_provider") or "groq").lower()
    if provider == "anthropic" and cfg.get("anthropic_key"):
        from pipecat.services.anthropic.llm import AnthropicLLMService

        return AnthropicLLMService(
            api_key=cfg["anthropic_key"],
            settings=AnthropicLLMService.Settings(
                model="claude-haiku-4-5", system_instruction=system_prompt
            ),
        )
    from pipecat.services.groq.llm import GroqLLMService

    return GroqLLMService(
        api_key=cfg.get("groq_key", ""),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile", system_instruction=system_prompt
        ),
    )


def _make_stt(lang, cfg: dict):
    """Returns (stt, needs_vad). Flux for en/hi; Nova-3 for te/ta."""
    from pipecat.transcriptions.language import Language

    key = cfg.get("deepgram_key", "")
    if lang.locale in ("te-IN", "ta-IN"):
        from pipecat.services.deepgram.stt import DeepgramSTTService

        dg_lang = {"te-IN": Language.TE, "ta-IN": Language.TA}[lang.locale]
        return DeepgramSTTService(
            api_key=key, settings=DeepgramSTTService.Settings(model="nova-3-general", language=dg_lang)
        ), True

    from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService

    if lang.llm_language == "english":
        model, hints = "flux-general-en", None
    else:
        model, hints = "flux-general-multi", [Language.HI]
    stt = DeepgramFluxSTTService(
        api_key=key,
        settings=DeepgramFluxSTTService.Settings(
            model=model, eot_threshold=0.7, language_hints=hints
        ),
        should_interrupt=True,
    )
    return stt, False


def _make_tts(lang, cfg: dict):
    speed = 1.0 if lang.llm_language == "english" else 0.92
    return ElevenLabsTTSService(
        api_key=cfg.get("elevenlabs_key", ""),
        settings=ElevenLabsTTSService.Settings(
            voice=cfg.get("elevenlabs_voice_id", "XrExE9yKIg1WjnnlVkGX"),
            model="eleven_flash_v2_5",
            stability=0.6,
            similarity_boost=0.8,
            speed=speed,
        ),
        auto_mode=True,
    )


async def run_interview(url: str, token: str, room: str, session_id: str, language: str,
                        strictness: str, cfg: dict) -> None:
    lang = get_language_config(language)
    profile = get_strictness_profile(_resolve_strictness(strictness))
    system_prompt = compose_system_prompt(SYSTEM_PROMPT, profile.level)
    directive = lang.language_directive()
    if directive:
        system_prompt = f"{system_prompt}\n\n{directive}"
    logger.info(f"[{session_id}] lang={lang.locale} strictness={profile.name}")

    stt, needs_vad = _make_stt(lang, cfg)
    tts = _make_tts(lang, cfg)
    llm = _make_llm(system_prompt, cfg)

    transport = LiveKitTransport(
        url,
        token,
        room,
        params=LiveKitParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    context = LLMContext()
    if needs_vad:
        user_agg, asst_agg = LLMContextAggregatorPair(
            context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
        )
    else:
        user_agg, asst_agg = LLMContextAggregatorPair(context)

    dynamics = Dynamics(context, silence_prompt_seconds=profile.silence_prompt_seconds)

    pipeline = Pipeline(
        [transport.input(), stt, dynamics, user_agg, llm, tts, LatencyLogger(),
         transport.output(), asst_agg]
    )
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))

    finalized = {"done": False}

    async def _finalize():
        if finalized["done"]:
            return
        finalized["done"] = True
        try:
            transcript = [
                {"role": m["role"], "content": m["content"]}
                for m in context.get_messages()
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
            ]
            answers = sum(1 for t in transcript if t["role"] == "user")
            sc = (
                generate_scorecard(transcript, cfg.get("groq_key", ""))
                if answers >= 1
                else {"verdict": "Borderline", "recommendation": "lean_no",
                      "summary": "Session ended before any answer."}
            )
            await storage.save_turns(session_id, transcript)
            await storage.save_scorecard(session_id, sc, dynamics.metadata.as_dict())
            await storage.set_session_status(session_id, "ended")
            logger.info(f"[{session_id}] saved — verdict={sc.get('verdict')}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{session_id}] finalize failed: {e}")

    @transport.event_handler("on_first_participant_joined")
    async def _on_join(transport, participant_id):
        greeting = _GREETINGS.get(lang.locale, _DEFAULT_GREETING)
        await task.queue_frames([TTSSpeakFrame(text=greeting, append_to_context=True)])

    @transport.event_handler("on_participant_disconnected")
    async def _on_left(transport, participant_id):
        await _finalize()
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
    await _finalize()  # safety net if the run ends without a 'left' event
