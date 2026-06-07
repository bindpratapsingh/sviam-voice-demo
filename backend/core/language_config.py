"""Language configuration & STT/TTS routing for the voice interviewer (Week 1 Deliverable 2).

Maps a session locale to the right Deepgram STT and TTS provider/voice, plus the prompt
rules that keep the AI reasoning in English while speaking the target language with
technical terms left in English.

All four languages run inside the existing Deepgram Voice Agent socket:
  - STT  : Deepgram Nova-3 covers en/en-IN/hi/te natively (Telugu added 2026-01-21).
           en-US stays on Nova-2 to exactly match current production behavior.
  - TTS  : Aura (English-only) for en-US; ElevenLabs (Turbo 2.5, WS-streamable) for
           en-IN / Hindi / Telugu, plugged into the Voice Agent `speak` slot.

Pure module: the ElevenLabs API key is passed IN by the orchestrator (which owns settings),
so this file imports nothing from app.config. Exact Voice-Agent field placement for the
ElevenLabs endpoint is verified against the live API during integration (Phase 3 of the plan).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.conversation_dynamics import (
    SAY_ACK_PAUSE,
    SAY_MOVE_ON,
    SAY_OFFER_REPHRASE,
    SAY_RESUME_ACK,
    SAY_TAKE_YOUR_TIME,
)

__all__ = [
    "LanguageConfig",
    "LANGUAGES",
    "LANGUAGE_CODES",
    "DEFAULT_LOCALE",
    "get_language_config",
]

DEFAULT_LOCALE = "en-US"

# ElevenLabs Turbo 2.5 is the only ElevenLabs model that supports WebSocket streaming
# (eleven_v3 does not — see WEEK1_VOICE_INTERVIEWER.md). Multilingual, low latency.
ELEVENLABS_MODEL = "eleven_turbo_v2_5"  # placeholder; swap for a custom multilingual model if desired

# Default ElevenLabs voice IDs per locale. These are starting defaults — swap for
# language-specialised female voices from the ElevenLabs account as desired.
# (Placeholders are clearly named so they are easy to find and replace.)
ELEVENLABS_VOICE_EN_IN = "1qEiC6qsybMkmnNdVMbK"  # your ElevenLabs multilingual voice
ELEVENLABS_VOICE_HI = "1qEiC6qsybMkmnNdVMbK"  # same voice for now (multilingual handles Hindi)
ELEVENLABS_VOICE_TE = "1qEiC6qsybMkmnNdVMbK"  # same voice for now (multilingual handles Telugu)


@dataclass(frozen=True)
class LanguageConfig:
    locale: str  # "en-US" | "en-IN" | "hi-IN" | "te-IN"
    deepgram_language: str  # Voice Agent agent.language value (e.g. "en", "hi", "te")
    stt_model: str  # Deepgram model id ("nova-2" | "nova-3")
    stt_streaming: bool  # True if streaming STT is supported for this language
    tts_provider: str  # "deepgram" | "eleven_labs"
    tts_voice: str  # Aura model id OR ElevenLabs voice id
    llm_language: str  # "english" | "hindi" | "telugu" (drives the prompt)
    elevenlabs_language_code: str = ""  # ISO code for ElevenLabs when applicable
    code_terms_english: bool = True  # ALWAYS True — technical terms stay English

    @property
    def overrides_persona_voice(self) -> bool:
        """Non-English locales speak through ElevenLabs, so the persona's Aura voice does not
        apply (persona character is conveyed via the prompt). English keeps the persona voice."""
        return self.tts_provider == "eleven_labs"

    def language_directive(self) -> str:
        """Prompt snippet appended to the system prompt to enforce the language rules."""
        if self.llm_language == "english":
            return ""
        lang = self.llm_language.title()
        return (
            f"LANGUAGE: Speak to the candidate in {lang}. Reason internally in English, but your "
            f"spoken output must be in {lang}. ALWAYS keep technical and programming terms in English "
            f"— e.g. 'hash map', 'sliding window', 'O(n)', 'return statement', 'binary tree', "
            f"'time complexity', 'API'. Do not translate code or code-related terminology."
        )

    def voice_agent_listen_config(self, keyterms: Optional[List[str]] = None) -> dict:
        """Build the Voice Agent `agent.listen` block for this language."""
        provider: dict = {"type": "deepgram", "model": self.stt_model, "smart_format": True}
        if keyterms:
            provider["keyterms"] = keyterms
        return {"provider": provider}

    def voice_agent_speak_config(self, *, persona_voice: str, elevenlabs_api_key: str = "") -> dict:
        """Build the Voice Agent `agent.speak` block.

        English → Deepgram Aura using the PERSONA's voice (unchanged from today).
        Non-English → ElevenLabs Turbo 2.5 using this locale's voice id.
        """
        if self.tts_provider == "eleven_labs":
            return {
                "provider": {
                    "type": "eleven_labs",
                    "model_id": ELEVENLABS_MODEL,
                    "language_code": self.elevenlabs_language_code,
                },
                "voice_id": self.tts_voice,
                "endpoint": {"headers": {"xi-api-key": elevenlabs_api_key}},
            }
        # Deepgram Aura — defer to the persona's configured voice.
        return {"provider": {"type": "deepgram", "model": persona_voice or self.tts_voice}}

    def tier_text(self, key: str) -> str:
        """Localized conversation-dynamics utterance (silence tiers, pause/resume ack) for this
        locale. Falls back to English (en-US) if the locale or key is missing."""
        return TIER_PROMPTS.get(self.locale, TIER_PROMPTS[DEFAULT_LOCALE]).get(key, "")


LANGUAGES: dict[str, LanguageConfig] = {
    "en-US": LanguageConfig(
        locale="en-US",
        deepgram_language="en",
        stt_model="nova-2",  # matches current production exactly (no regression)
        stt_streaming=True,
        tts_provider="deepgram",
        tts_voice="aura-asteria-en",  # fallback; persona voice takes precedence for English
        llm_language="english",
    ),
    "en-IN": LanguageConfig(
        locale="en-IN",
        deepgram_language="en-IN",
        stt_model="nova-3",
        stt_streaming=True,
        tts_provider="eleven_labs",
        tts_voice=ELEVENLABS_VOICE_EN_IN,
        llm_language="english",
        elevenlabs_language_code="en",
    ),
    "hi-IN": LanguageConfig(
        locale="hi-IN",
        deepgram_language="hi",
        stt_model="nova-3",
        stt_streaming=True,
        tts_provider="eleven_labs",
        tts_voice=ELEVENLABS_VOICE_HI,
        llm_language="hindi",
        elevenlabs_language_code="hi",
    ),
    "te-IN": LanguageConfig(
        locale="te-IN",
        deepgram_language="te",
        stt_model="nova-3",  # Telugu added to Nova-3 on 2026-01-21 (streaming); verify in Phase 3
        stt_streaming=True,
        tts_provider="eleven_labs",
        tts_voice=ELEVENLABS_VOICE_TE,
        llm_language="telugu",
        elevenlabs_language_code="te",
    ),
    # Tamil — Indian language (per meeting). Flux has no Tamil turn-taking, so STT runs on
    # Nova-3 (streaming) + ElevenLabs TTS (both verified). Telugu (te-IN above) works the same way.
    "ta-IN": LanguageConfig(
        locale="ta-IN",
        deepgram_language="ta",
        stt_model="nova-3",
        stt_streaming=True,
        tts_provider="eleven_labs",
        tts_voice=ELEVENLABS_VOICE_EN_IN,
        llm_language="tamil",
        elevenlabs_language_code="ta",
    ),
}

LANGUAGE_CODES = tuple(LANGUAGES.keys())


# Localized conversation-dynamics utterances (silence tiers + pause/resume acks).
# English for en-US and en-IN; Hindi/Telugu are starter translations — refine with a native speaker.
_ENGLISH_TIERS = {
    "take_your_time": SAY_TAKE_YOUR_TIME,
    "offer_rephrase": SAY_OFFER_REPHRASE,
    "move_on": SAY_MOVE_ON,
    "ack_pause": SAY_ACK_PAUSE,
    "resume_ack": SAY_RESUME_ACK,
}

TIER_PROMPTS: dict[str, dict[str, str]] = {
    "en-US": _ENGLISH_TIERS,
    "en-IN": _ENGLISH_TIERS,
    "hi-IN": {
        "take_your_time": "अपना समय लीजिए। जब आप तैयार हों तो मुझे बता दीजिए।",
        "offer_rephrase": "क्या मैं सवाल को दूसरे तरीके से पूछूँ?",
        "move_on": "मैं अगले विषय पर बढ़ता हूँ। हम बाद में इस पर वापस आ सकते हैं।",
        "ack_pause": "बिल्कुल, अपना समय लीजिए।",
        "resume_ack": "बढ़िया, चलिए आगे बढ़ते हैं।",
    },
    "te-IN": {
        "take_your_time": "మీ సమయం తీసుకోండి. మీరు సిద్ధంగా ఉన్నప్పుడు నాకు చెప్పండి.",
        "offer_rephrase": "ప్రశ్నను నేను మరో విధంగా అడగమంటారా?",
        "move_on": "నేను తదుపరి అంశానికి వెళ్తాను. మనం తర్వాత దీనికి తిరిగి రావచ్చు.",
        "ack_pause": "తప్పకుండా, మీ సమయం తీసుకోండి.",
        "resume_ack": "బాగుంది, కొనసాగిద్దాం.",
    },
}


def get_language_config(locale: Optional[str]) -> LanguageConfig:
    """Return the config for a locale, defaulting safely to en-US on anything invalid."""
    if not locale:
        return LANGUAGES[DEFAULT_LOCALE]
    return LANGUAGES.get(locale.strip(), LANGUAGES[DEFAULT_LOCALE])
