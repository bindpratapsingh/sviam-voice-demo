"""Dynamics — Week-1 Deliverable 1 (conversation dynamics) as a Pipecat processor,
wrapping the ported, unit-tested core.conversation_dynamics.

For every user turn (from Flux) it:
  - classifies the turn (answer / ask-back / pause / resume) — deterministic + tested,
  - tracks scorecard METADATA (clarifications, edge-case clarifiers, pauses,
    interruptions, stalls) for P7,
  - LOGS what fired (so the live demo + terminal show the dynamics working),
  - STEERS Aria for pause / resume / ask-back by injecting a brief, ephemeral hint
    into the LLM context, so she behaves deterministically in her own voice
    (rephrase-not-repeat, no penalty; "take your time" then wait).

Placed AFTER the STT and BEFORE the user aggregator, so the context hint lands
before the aggregator triggers LLM generation.

NOTE: the silence-escalation state machine (tiered "take your time / rephrase /
move on" prompts) needs a background ticker tied to the pipeline task; that is a
follow-up (P4b). Pause/ask-back/resume + metadata are live here.

Off by default; enable with DYNAMICS=on.
"""

from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from core.conversation_dynamics import ConversationDynamics, DirectiveType


class Dynamics(FrameProcessor):
    def __init__(self, context, *, silence_prompt_seconds: int = 30):
        super().__init__()
        self._cd = ConversationDynamics(silence_prompt_seconds=silence_prompt_seconds)
        self._context = context

    @property
    def metadata(self):
        return self._cd.metadata

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._cd.on_ai_started_speaking()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._cd.on_ai_finished_speaking()
        elif isinstance(frame, UserStartedSpeakingFrame):
            # Tracks an interruption if the bot was mid-utterance (barge-in aftermath).
            self._cd.on_user_started_speaking()
        elif isinstance(frame, TranscriptionFrame) and (frame.text or "").strip():
            directive = self._cd.on_user_text(frame.text)
            self._narrate(directive)
            self._maybe_steer(directive)

        await self.push_frame(frame, direction)

    def _narrate(self, directive) -> None:
        dt = directive.type
        if dt is DirectiveType.ACKNOWLEDGE_PAUSE:
            logger.info("⏸  pause requested → acknowledge + wait (silence timer frozen)")
        elif dt is DirectiveType.RESUME:
            logger.info("▶️  resume → continue")
        elif dt is DirectiveType.REPHRASE and directive.reason == "ask_back":
            extra = " (edge-case → credit)" if directive.credit_edge_case else ""
            stall = " [stall flagged]" if directive.stall_flagged else ""
            logger.info(f"🔁 ask-back → rephrase, no penalty{extra}{stall}")

    def _maybe_steer(self, directive) -> None:
        """Inject a brief, ephemeral steering hint so Aria does the right thing in her
        own voice. Ask-back/pause/resume only — plain answers are untouched."""
        hint = None
        if directive.type is DirectiveType.ACKNOWLEDGE_PAUSE:
            hint = (
                "The candidate asked for a moment to think. Reply with ONLY a brief, warm "
                "acknowledgement such as 'Of course — take your time, let me know when you're "
                "ready.' Do NOT ask a question, give a hint, restate the problem, or add anything "
                "else this turn. Then wait."
            )
        elif directive.type is DirectiveType.RESUME:
            hint = (
                "The candidate is ready to continue. Briefly acknowledge, then continue "
                "with your current question."
            )
        elif directive.type is DirectiveType.REPHRASE and directive.reason == "ask_back":
            hint = (
                "The candidate asked for clarification. REPHRASE your last question "
                "differently (never verbatim), do NOT penalize them, and do not give the answer."
            )
        if hint:
            self._context.add_message({"role": "developer", "content": hint})
