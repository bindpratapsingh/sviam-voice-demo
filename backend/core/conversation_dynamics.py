"""Conversation dynamics for the live voice interviewer.

Pure, dependency-free logic (no I/O, no app.config, no network) so it is fully
unit-testable and safe to call from the WebSocket loop. The orchestrator feeds
events in (AI started/stopped speaking, user started speaking, user said X,
silence tick) and gets back a `Directive` describing what the agent should do.

Covers Week-1 Deliverable 1:
  1.1 Barge-in aftermath  — don't repeat the cut-off line; respond to what was said
  1.2 Pause/silence       — strictness-scaled state machine (think → prompt → rephrase → move on)
  1.3 Ask-back            — detect clarification, rephrase (not repeat), credit edge cases, no penalty
  1.3 Stall detection     — flag >3 ask-backs on the same topic
  1.4 Resumption          — explicit pause/resume + pending-thread tracking + metadata

The actual <200ms TTS cut is a frontend-playback concern (see WEEK1_VOICE_INTERVIEWER.md);
this module owns the *behavioral* aftermath, not the audio stream.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List

__all__ = [
    "TurnType",
    "DirectiveType",
    "SilenceStage",
    "TurnClassification",
    "Directive",
    "SilenceThresholds",
    "DynamicsMetadata",
    "ConversationDynamics",
    "classify_turn",
    "GRACE_SECONDS",
]

# ── Tunables ──────────────────────────────────────────────────────────────────
GRACE_SECONDS = 5  # never prompt before this many seconds of silence (doc 1.2 "do nothing")
DEFAULT_STALL_THRESHOLD = 3  # >3 ask-backs on one topic = stalling (doc 1.3)

# Canonical AI utterances (doc 1.2). Kept verbatim so behavior matches the spec.
SAY_TAKE_YOUR_TIME = "Take your time. Let me know when you're ready."
SAY_OFFER_REPHRASE = "Would you like me to rephrase the question?"
SAY_MOVE_ON = "I'll move on to the next topic. We can circle back later."
SAY_ACK_PAUSE = "Of course — take your time."
SAY_RESUME_ACK = "Great, let's continue."


class TurnType(str, Enum):
    """What a candidate utterance is, behaviorally."""

    ANSWER = "answer"
    ASK_BACK = "ask_back"  # a clarification question directed at the AI
    PAUSE_REQUEST = "pause_request"  # "can I have a moment"
    RESUME_REQUEST = "resume_request"  # "I'm ready"


class DirectiveType(str, Enum):
    """What the orchestrator should do next."""

    NONE = "none"
    SAY = "say"  # inject `text` verbatim
    REPHRASE = "rephrase"  # re-ask the current question differently (never verbatim)
    MOVE_ON = "move_on"  # advance to the next topic
    ACKNOWLEDGE_PAUSE = "acknowledge_pause"
    RESUME = "resume"


class SilenceStage(int, Enum):
    """Ordered silence escalation stages (ordering matters for fire-once logic)."""

    THINKING = 0  # 0..tier1 — normal thinking time, do nothing
    GENTLE = 1  # tier1 — "Take your time…"
    REPHRASE = 2  # tier2 — "Would you like me to rephrase?"
    MOVE_ON = 3  # tier3 — "I'll move on…"


@dataclass
class TurnClassification:
    turn_type: TurnType
    is_edge_case_clarifier: bool = False  # e.g. "does this handle negatives?" → credit-worthy
    matched_pattern: str = ""


@dataclass
class Directive:
    type: DirectiveType
    text: str = ""
    reason: str = ""
    credit_edge_case: bool = False  # caller should credit edge-case thinking in the scorecard
    stall_flagged: bool = False  # caller should note stalling (still answers, never penalizes)


@dataclass
class SilenceThresholds:
    """Silence escalation offsets in seconds. Level 2 reproduces the doc's 5/30/90/120."""

    tier1: float  # gentle prompt        (= silence_prompt_seconds)
    tier2: float  # rephrase offer        (= 3×)
    tier3: float  # move on               (= 4×)

    @classmethod
    def from_strictness(cls, silence_prompt_seconds: int) -> "SilenceThresholds":
        s = float(max(GRACE_SECONDS, silence_prompt_seconds))
        return cls(tier1=s, tier2=3.0 * s, tier3=4.0 * s)


@dataclass
class DynamicsMetadata:
    """Per-session signals surfaced to the scorecard. Never used to penalize ask-backs."""

    clarifications_asked: int = 0
    edge_case_clarifiers: int = 0
    pauses_taken: int = 0
    interruptions: int = 0
    stalls_flagged: int = 0

    def as_dict(self) -> dict:
        return {
            "clarifications_asked": self.clarifications_asked,
            "edge_case_clarifiers": self.edge_case_clarifiers,
            "pauses_taken": self.pauses_taken,
            "interruptions": self.interruptions,
            "stalls_flagged": self.stalls_flagged,
        }

    def summary(self) -> str:
        parts: List[str] = []
        if self.clarifications_asked:
            parts.append(f"asked for clarification {self.clarifications_asked}x")
        if self.edge_case_clarifiers:
            parts.append(f"raised edge cases {self.edge_case_clarifiers}x")
        if self.pauses_taken:
            parts.append(f"took {self.pauses_taken} pause(s)")
        if self.interruptions:
            parts.append(f"interrupted the interviewer {self.interruptions}x")
        if self.stalls_flagged:
            parts.append(f"possible stalling flagged {self.stalls_flagged}x")
        return "; ".join(parts)


# ── Intent patterns ───────────────────────────────────────────────────────────
# Order of evaluation in classify_turn: resume → pause → ask-back → edge-case-question.

_RESUME_PATTERNS = [
    r"\bi'?m ready\b",
    r"\bi am ready\b",
    r"\bready to (go|start|continue|begin)\b",
    r"\bgo ahead\b",
    r"\blet'?s (go|continue|start|begin)\b",
    r"\bi'?m done thinking\b",
    r"\bi'?m good (to go|now)\b",
    # Hindi
    r"तैयार (हूँ|हूं|है)",
    r"आगे बढ़",
    r"चलो (आगे|शुरू|जारी)",
]

_PAUSE_PATTERNS = [
    r"\bcan i (have|get|take) a (moment|minute|second|sec)\b",
    r"\b(give|just give) me a (moment|minute|second|sec)\b",
    r"\bgive me a sec\b",
    r"\blet me think\b",
    r"\bneed a (moment|minute|second|sec)\b",
    r"\bhold on\b",
    r"\bone (moment|second|sec|minute)\b",
    r"\bjust a (moment|second|sec|minute)\b",
    # broaden: "give me two minutes", "a couple minutes", "some time to think", "a bit"
    r"\b(can|could) (you|i) (give me|have|get|take) .{0,12}(minute|minutes|moment|moments|second|seconds)\b",
    r"\b(give|just give) me (a couple|a few|two|three|four|five|\d+|some) (minute|minutes|moment|moments|second|seconds)\b",
    r"\bneed (a couple|a few|two|three|\d+|some) (minute|minutes|moment|moments|second|seconds)\b",
    r"\b(a couple|a few|couple of) (minutes|seconds|moments)\b",
    r"\bgive me (some time|a bit|a minute or two)\b",
    r"\bsome time to (think|prepare|gather)\b",
    r"\bgive me .{0,10}(minute|minutes|second|seconds)\b",  # "give me दो minutes" (mixed)
    # Hindi: रुको / समय दो / सोचने दो / दो मिनट
    r"रुक(ो|िए|ें|िये)",
    r"(एक|दो|तीन|कुछ|थोड़ा|थोड़ी|\d+)\s*(मिनट|सेकंड|सेकेंड|पल)",
    r"(समय|वक्त|टाइम)\s*(दो|दीजिए|दीजि|चाहिए|दे दो)",
    r"सोचने\s*(दो|दीजिए|दे|का समय|का वक्त)",
]

_ASKBACK_PATTERNS = [
    r"\bcan you repeat\b",
    r"\bcould you repeat\b",
    r"\brepeat that\b",
    r"\bsay that again\b",
    r"\bcome again\b",
    r"\bwhat do you mean\b",
    r"\bwhat does .+ mean\b",
    r"\bwhat'?s .+ mean\b",
    r"\bdo you mean\b",
    r"\bare you asking\b",
    r"\bis that asking\b",
    r"\b(can|could) you (clarify|rephrase|explain)\b",
    r"\bsorry,? i did ?n'?t (catch|hear|get|understand)\b",
    r"\bi did ?n'?t (catch|hear|get|understand)\b",
    r"\bnot sure what you (mean|meant)\b",
    # Hindi: दोहराओ / फिर से / क्या मतलब / समझ नहीं
    r"दोहरा",
    r"दुबारा",
    r"फिर से (बोल|कह|बता|कहि|सुना)",
    r"क्या मतलब",
    r"समझ(ा)? नहीं",
]

_EDGE_CASE_PATTERNS = [
    r"\bnegative (number|numbers|value|values|input|inputs)\b",
    r"\bempty (input|array|list|string)\b",
    r"\bnull\b",
    r"\bduplicate",
    r"\b(un)?sorted\b",
    r"\bedge case",
    r"\bconstraint",
    r"\bguaranteed\b",
    r"\bshould i (handle|assume|consider)\b",
    r"\bdo i (need to|have to) handle\b",
    r"\bcan the input\b",
    r"\bwhat if\b",
    r"\bis it guaranteed\b",
    r"\binput (size|range|length|bounds)\b",
    r"\bhow (large|big|long)\b",
    r"\bcan (it|there|they) be\b",
]

_RESUME_RE = [re.compile(p) for p in _RESUME_PATTERNS]
_PAUSE_RE = [re.compile(p) for p in _PAUSE_PATTERNS]
_ASKBACK_RE = [re.compile(p) for p in _ASKBACK_PATTERNS]
_EDGE_CASE_RE = [re.compile(p) for p in _EDGE_CASE_PATTERNS]

# Short affirmations that mean "resume" only when we are already paused.
_SHORT_AFFIRMATIONS = {"ok", "okay", "yes", "yeah", "yep", "ready", "done", "sure", "go"}


def _first_match(text: str, patterns: List[re.Pattern]) -> str:
    for pat in patterns:
        if pat.search(text):
            return pat.pattern
    return ""


def classify_turn(text: str) -> TurnClassification:
    """Classify a candidate utterance (context-free). The stateful resume-on-bare-'okay'
    handling lives in ConversationDynamics, which knows whether we're paused."""
    t = (text or "").lower().strip()
    if not t:
        return TurnClassification(TurnType.ANSWER)

    m = _first_match(t, _RESUME_RE)
    if m:
        return TurnClassification(TurnType.RESUME_REQUEST, matched_pattern=m)

    m = _first_match(t, _PAUSE_RE)
    if m:
        return TurnClassification(TurnType.PAUSE_REQUEST, matched_pattern=m)

    m = _first_match(t, _ASKBACK_RE)
    if m:
        edge = bool(_first_match(t, _EDGE_CASE_RE))
        return TurnClassification(TurnType.ASK_BACK, is_edge_case_clarifier=edge, matched_pattern=m)

    # A bare edge-case question with no explicit ask-back trigger is still a clarifier,
    # e.g. "Does this need to handle negative numbers?"
    if t.endswith("?"):
        m = _first_match(t, _EDGE_CASE_RE)
        if m:
            return TurnClassification(TurnType.ASK_BACK, is_edge_case_clarifier=True, matched_pattern=m)

    return TurnClassification(TurnType.ANSWER)


class _SilenceTracker:
    """Fires each escalation stage exactly once per question."""

    def __init__(self, thresholds: SilenceThresholds) -> None:
        self.thresholds = thresholds
        self._fired = SilenceStage.THINKING

    def reset(self) -> None:
        self._fired = SilenceStage.THINKING

    def _stage_for(self, elapsed: float) -> SilenceStage:
        if elapsed >= self.thresholds.tier3:
            return SilenceStage.MOVE_ON
        if elapsed >= self.thresholds.tier2:
            return SilenceStage.REPHRASE
        if elapsed >= self.thresholds.tier1:
            return SilenceStage.GENTLE
        return SilenceStage.THINKING

    def evaluate(self, elapsed: float) -> Directive:
        stage = self._stage_for(elapsed)
        if stage.value <= self._fired.value:
            return Directive(DirectiveType.NONE)
        self._fired = stage
        if stage is SilenceStage.GENTLE:
            return Directive(DirectiveType.SAY, SAY_TAKE_YOUR_TIME, reason="silence_tier1")
        if stage is SilenceStage.REPHRASE:
            return Directive(DirectiveType.REPHRASE, SAY_OFFER_REPHRASE, reason="silence_tier2")
        return Directive(DirectiveType.MOVE_ON, SAY_MOVE_ON, reason="silence_tier3")


class ConversationDynamics:
    """Stateful per-session conversation manager.

    Usage from the orchestrator:
        cd = ConversationDynamics(silence_prompt_seconds=profile.silence_prompt_seconds)
        cd.set_question(topic="two-sum", question="Walk me through your approach.")
        cd.on_ai_started_speaking() / cd.on_ai_finished_speaking()
        directive = cd.on_user_started_speaking()   # barge-in aftermath
        directive = cd.on_user_text("can you repeat that?")
        directive = cd.on_silence_tick(elapsed_seconds)
    """

    def __init__(
        self,
        *,
        silence_prompt_seconds: int = 30,
        stall_threshold: int = DEFAULT_STALL_THRESHOLD,
    ) -> None:
        self.thresholds = SilenceThresholds.from_strictness(silence_prompt_seconds)
        self.metadata = DynamicsMetadata()
        self._silence = _SilenceTracker(self.thresholds)
        self._askback_counts: dict[str, int] = {}
        self._stall_threshold = stall_threshold
        self.current_topic = ""
        self.pending_question = ""
        self.ai_speaking = False
        self.paused = False
        self.interrupted_text = ""  # what the AI was saying when interrupted (do NOT repeat)

    # ── Question lifecycle ──
    def set_question(self, topic: str, question: str) -> None:
        self.current_topic = topic or "general"
        self.pending_question = question
        self.paused = False
        self.interrupted_text = ""
        self._silence.reset()

    # ── AI speech events ──
    def on_ai_started_speaking(self) -> None:
        self.ai_speaking = True

    def on_ai_finished_speaking(self, text: str = "") -> None:
        self.ai_speaking = False

    # ── User speech events ──
    def on_user_started_speaking(self) -> Directive:
        """Called the instant the candidate's voice is detected. If the AI was talking,
        this is a barge-in: the frontend cuts playback; here we record state so the AI
        does NOT repeat its cut-off line and instead responds to what the user says."""
        self._silence.reset()
        if self.ai_speaking:
            self.metadata.interruptions += 1
            self.interrupted_text = self.pending_question
            self.ai_speaking = False
            return Directive(
                DirectiveType.NONE,
                reason="barge_in: cut playback, do not repeat, await user turn",
            )
        return Directive(DirectiveType.NONE, reason="user_started_speaking")

    def on_user_text(self, text: str) -> Directive:
        """Called when a candidate utterance is transcribed. Resets the silence timer and
        returns the appropriate behavioral directive."""
        self._silence.reset()
        cls = classify_turn(text)
        t = (text or "").lower().strip()

        # Resume from an explicit pause (full phrase or a bare affirmation while paused).
        if self.paused and (
            cls.turn_type is TurnType.RESUME_REQUEST or t in _SHORT_AFFIRMATIONS
        ):
            self.paused = False
            return Directive(DirectiveType.RESUME, SAY_RESUME_ACK, reason="resume")

        if cls.turn_type is TurnType.PAUSE_REQUEST:
            self.paused = True
            self.metadata.pauses_taken += 1
            return Directive(DirectiveType.ACKNOWLEDGE_PAUSE, SAY_ACK_PAUSE, reason="pause_request")

        if cls.turn_type is TurnType.RESUME_REQUEST:
            self.paused = False
            return Directive(DirectiveType.RESUME, SAY_RESUME_ACK, reason="resume")

        if cls.turn_type is TurnType.ASK_BACK:
            topic = self.current_topic or "general"
            self._askback_counts[topic] = self._askback_counts.get(topic, 0) + 1
            count = self._askback_counts[topic]
            self.metadata.clarifications_asked += 1
            if cls.is_edge_case_clarifier:
                self.metadata.edge_case_clarifiers += 1
            stalling = count > self._stall_threshold
            if stalling:
                self.metadata.stalls_flagged += 1
            # Rephrase (never verbatim). Credit edge-case thinking. Note stall but still answer.
            return Directive(
                DirectiveType.REPHRASE,
                reason="ask_back",
                credit_edge_case=cls.is_edge_case_clarifier,
                stall_flagged=stalling,
            )

        # Plain answer — resolves the pending thread, clears any pause.
        self.paused = False
        self.interrupted_text = ""
        return Directive(DirectiveType.NONE, reason="answer")

    # ── Silence tick ──
    def on_silence_tick(self, elapsed_seconds: float) -> Directive:
        """Called periodically with seconds since the candidate last spoke. While paused,
        the timer is frozen (no prompts)."""
        if self.paused:
            return Directive(DirectiveType.NONE, reason="paused")
        return self._silence.evaluate(elapsed_seconds)

    def reset_silence(self) -> None:
        self._silence.reset()
