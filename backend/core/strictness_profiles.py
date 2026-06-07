"""Strictness profiles for the voice interviewer (Week 1 Deliverable 3).

Four modes change the interviewer's *personality and pressure* — never the scoring,
never the question difficulty, never fairness. A profile contributes:
  - a system-prompt addon (appended to the persona prompt) — "the prompts are the product"
  - operational thresholds (interrupt sensitivity, follow-up depth, silence timing, hints)

Pure module: no app.config / network / scoring imports, so it cannot affect evaluation.
The "actively mislead" hint policy from the original brief is intentionally replaced with
WITHHOLD_PRESSURE — maximum pressure, zero hints, but never states a false technical fact
(hiring fairness / legal safety; see WEEK1_VOICE_INTERVIEWER.md §8).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "HintPolicy",
    "StrictnessProfile",
    "STRICTNESS_PROFILES",
    "STRICTNESS_LEVELS",
    "DEFAULT_STRICTNESS",
    "get_strictness_profile",
    "compose_system_prompt",
]

STRICTNESS_LEVELS = (1, 2, 3, 4)
DEFAULT_STRICTNESS = 2


class HintPolicy(str, Enum):
    FREELY = "freely"  # offer hints when stuck
    AFTER_STRUGGLE = "after_struggle"  # hint only after repeated failed attempts
    NEVER = "never"  # no hints, but neutral
    WITHHOLD_PRESSURE = "withhold_pressure"  # no hints + maximum pushback (never false facts)


@dataclass(frozen=True)
class StrictnessProfile:
    level: int  # 1-4
    name: str  # friendly | standard | tough | adversarial
    system_prompt_addon: str  # appended to the base/persona system prompt
    interrupt_threshold: float  # 0.0 (never interrupt) … 1.0 (interrupt on anything imprecise)
    max_followups: int  # per topic
    silence_prompt_seconds: int  # before the first silence prompt (feeds ConversationDynamics)
    hint_policy: HintPolicy


# ── The four profiles. Addons are written to compose cleanly with any persona. ──

_FRIENDLY_ADDON = (
    "STRICTNESS: FRIENDLY. Be warm, supportive, and encouraging. This is a calm, low-pressure "
    "conversation. Rarely interrupt — let the candidate finish their thought. When they stumble, "
    "reassure them ('That's a good start — can you build on it?') and offer a gentle hint if they "
    "are clearly stuck. Acknowledge good reasoning. Never badger. Your goal is to help the candidate "
    "show their best thinking. Do NOT lower the technical bar — ask the same substantive questions, "
    "just deliver them kindly."
)

_STANDARD_ADDON = (
    "STRICTNESS: STANDARD. Be balanced, neutral, and professional. Ask a follow-up when an answer is "
    "vague or incomplete. Interrupt only when the candidate contradicts themselves or their code. "
    "Probe for the 'why' behind decisions. Give a hint only after the candidate has genuinely "
    "struggled. Stay courteous and even-handed throughout."
)

_TOUGH_ADDON = (
    "STRICTNESS: TOUGH. Be direct and demanding, with no hand-holding. Push back on vague or hand-wavy "
    "answers ('That's not specific enough — give me the exact complexity'). Interrupt more readily when "
    "reasoning is loose. Expect precision and require the candidate to justify trade-offs. Do NOT offer "
    "hints. Remain respectful and fair, but keep the pressure high. The questions and bar are the same "
    "as any other interview — only your manner is tougher."
)

_ADVERSARIAL_ADDON = (
    "STRICTNESS: ADVERSARIAL. Play devil's advocate and challenge everything. Demand proof for every "
    "claim ('I don't buy that — prove it'). Interrupt frequently the moment an answer is imprecise. "
    "Apply maximum pressure and offer no hints whatsoever. Pressure-test the candidate's confidence by "
    "pushing back hard on their reasoning and forcing them to defend it.\n"
    "ABSOLUTE RULE: never state a false technical fact, never feed misleading information, and never "
    "fabricate errors in correct code. Your pressure comes from rigor and skepticism, not deception. "
    "This challenges the experience only — it must NOT change how the candidate is scored, and the "
    "technical questions and difficulty stay identical to every other interview."
)

STRICTNESS_PROFILES: dict[int, StrictnessProfile] = {
    1: StrictnessProfile(
        level=1,
        name="friendly",
        system_prompt_addon=_FRIENDLY_ADDON,
        interrupt_threshold=0.05,
        max_followups=1,
        silence_prompt_seconds=60,
        hint_policy=HintPolicy.FREELY,
    ),
    2: StrictnessProfile(
        level=2,
        name="standard",
        system_prompt_addon=_STANDARD_ADDON,
        interrupt_threshold=0.40,
        max_followups=2,
        silence_prompt_seconds=30,
        hint_policy=HintPolicy.AFTER_STRUGGLE,
    ),
    3: StrictnessProfile(
        level=3,
        name="tough",
        system_prompt_addon=_TOUGH_ADDON,
        interrupt_threshold=0.70,
        max_followups=3,
        silence_prompt_seconds=20,
        hint_policy=HintPolicy.NEVER,
    ),
    4: StrictnessProfile(
        level=4,
        name="adversarial",
        system_prompt_addon=_ADVERSARIAL_ADDON,
        interrupt_threshold=0.90,
        max_followups=5,  # "4+ until satisfied"
        silence_prompt_seconds=15,
        hint_policy=HintPolicy.WITHHOLD_PRESSURE,
    ),
}


def get_strictness_profile(level: int | None) -> StrictnessProfile:
    """Return the profile for a level, defaulting safely to Standard (2) on anything invalid."""
    try:
        lvl = int(level)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        lvl = DEFAULT_STRICTNESS
    return STRICTNESS_PROFILES.get(lvl, STRICTNESS_PROFILES[DEFAULT_STRICTNESS])


def compose_system_prompt(base_prompt: str, level: int | None) -> str:
    """Append the strictness addon to a persona/base system prompt.

    Persona governs *character*; strictness governs *intensity*. They are orthogonal and
    compose by concatenation.
    """
    profile = get_strictness_profile(level)
    base = (base_prompt or "").rstrip()
    if not base:
        return profile.system_prompt_addon
    return f"{base}\n\n{profile.system_prompt_addon}"
