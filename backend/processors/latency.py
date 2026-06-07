"""LatencyLogger — measures the conversational latency that actually matters:
the gap between the user finishing their turn (EndOfTurn) and the FIRST audio
the bot speaks back. This is the number we report for the demo.

It keys off two frames that both flow downstream, so it works for either STT mode:
  - UserStoppedSpeakingFrame : emitted when the user's turn ends (Flux EoT / VAD stop)
  - TTSAudioRawFrame         : the first chunk of the bot's spoken reply

Place it right after the TTS service in the pipeline.
"""

import time

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class LatencyLogger(FrameProcessor):
    """Logs EoT → first-bot-audio latency, once per turn."""

    def __init__(self):
        super().__init__()
        self._eot_ts: float | None = None
        self._logged_this_turn = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            # New user turn (or a barge-in): arm a fresh measurement.
            self._eot_ts = None
            self._logged_this_turn = False
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._eot_ts = time.monotonic()
            self._logged_this_turn = False
        elif (
            isinstance(frame, TTSAudioRawFrame)
            and self._eot_ts is not None
            and not self._logged_this_turn
        ):
            ms = (time.monotonic() - self._eot_ts) * 1000.0
            logger.info(f"⚡ Response latency (EndOfTurn → first audio): {ms:.0f} ms")
            self._logged_this_turn = True

        await self.push_frame(frame, direction)
