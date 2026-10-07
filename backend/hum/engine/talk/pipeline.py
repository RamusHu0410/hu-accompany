"""One talk turn: (recording →) words → Gemini's edit → checked edit → new settings and a reply to speak.

The pipeline never raises. If a service fails, the settings stay the same and the reply
says so kindly. Speaking the reply is a separate step (see tts.py), so it can stream.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import phrases
from .commands import Command
from .edits import check, describe
from .settings import SongSettings, apply_command, blocked_adjustments, changed_fields

Understand = Callable[[str, SongSettings, str | None], Command]  # the words, the song, the gnome's personality
Transcribe = Callable[[bytes, str], str]

log = logging.getLogger(__name__)


@dataclass
class Turn:
    heard: str
    intent: str  # adjust | undo | off_topic | unclear | error
    settings: SongSettings
    reply: str
    changed: list[str] = field(default_factory=list)
    understood: list[str] = field(default_factory=list)  # what the edit did, e.g. "✓ Keep piano", "+ Add violin — soft, in the background"
    timings: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "heard": self.heard,
            "intent": self.intent,
            "settings": self.settings.to_dict(),
            "changed": self.changed,
            "understood": self.understood,
            "reply": self.reply,
            "timings": self.timings,
            "error": self.error,
        }


class Pipeline:
    def __init__(self, understand: Understand, transcribe: Transcribe | None = None):
        self._understand = understand
        self._transcribe = transcribe

    def from_text(self, text: str, current: SongSettings, previous: SongSettings | None = None, personality: str | None = None) -> Turn:
        started = time.perf_counter()
        return self._interpret((text or "").strip(), current, previous, personality, {}, started)

    def from_audio(
        self, audio: bytes, filename: str, current: SongSettings, previous: SongSettings | None = None, personality: str | None = None
    ) -> Turn:
        started = time.perf_counter()
        timings: dict[str, int] = {}
        try:
            heard = self._transcribe(audio, filename)
        except Exception as exc:
            log.exception("speech to text failed")
            return _finish(Turn("", "error", current, phrases.EARS_FAILED, error=_describe(exc)), timings, started)
        timings["transcribe_ms"] = _ms_since(started)
        if not heard:
            return _finish(Turn("", "unclear", current, phrases.NOTHING_HEARD), timings, started)
        return self._interpret(heard, current, previous, personality, timings, started)

    def _interpret(self, text, current, previous, personality, timings, started) -> Turn:
        if not text:
            return _finish(Turn("", "unclear", current, phrases.NOTHING_TYPED), timings, started)
        asked = time.perf_counter()
        try:
            command = self._understand(text, current, personality)
        except Exception as exc:
            log.exception("understanding failed")
            return _finish(Turn(text, "error", current, phrases.LOST_THOUGHT, error=_describe(exc)), timings, started)
        timings["understand_ms"] = _ms_since(asked)
        return _finish(_decide(text, command, current, previous), timings, started)


def _decide(text: str, command: Command, current: SongSettings, previous: SongSettings | None) -> Turn:
    """Turns Gemini's answer into the new settings. Only 'adjust' and 'undo' may change anything,
    and an edit is first checked against what the listener said (edits.py)."""
    if command.intent == "undo":
        if previous is None:
            return Turn(text, "undo", current, phrases.NOTHING_TO_UNDO)
        return Turn(text, "undo", previous, command.reply or phrases.UNDONE, changed_fields(current, previous), describe(current, previous))
    if command.intent != "adjust":
        fallback = phrases.NOTHING_TYPED if command.intent == "unclear" else phrases.OFF_TOPIC
        return Turn(text, command.intent, current, command.reply or fallback)
    command, notes = check(command, current, text)
    updated = apply_command(current, command)
    changed = changed_fields(current, updated)
    if not changed:
        return Turn(text, "adjust", current, " ".join(notes) or phrases.already_there(blocked_adjustments(current, command)))
    reply = phrases.done_but(notes) if notes else command.reply or phrases.DONE  # Gemini's reply described the edit before it was corrected
    return Turn(text, "adjust", updated, reply, changed, describe(current, updated))


def _finish(turn: Turn, timings: dict[str, int], started: float) -> Turn:
    turn.timings = {**timings, "total_ms": _ms_since(started)}
    return turn


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]
