"""One chat turn: (a recording →) words → Gemini's edits → the edited project and a reply to show and speak.

Never raises. When a service fails or nothing could be done, the project comes back unchanged (None)
and the reply says why. Undo and redo are the app's: it keeps the history, so the turn only names
the intent (the app says whether there is anything to undo, so the reply can be honest).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hum.song.project import Project

from .commands import Answer
from .executor import apply
from .interpreter import GeminiBusy

Understand = Callable[[str, Project], Answer]
Transcribe = Callable[[bytes, str], str]

log = logging.getLogger(__name__)


class MissingKey(RuntimeError):
    """An API key isn't set; the message says which, and that's what the listener is told."""


NOTHING_HEARD = "I didn't hear anything. Try again a little closer to the mic, or type it."
EARS_FAILED = "I couldn't make out the recording just now. Try again, or type it."
NOTHING_TYPED = "Tell me what to change, like 'softer drums' or 'make it jazz'."
BUSY = "I'm getting a lot of requests right now. Give me a few seconds and try again."
BRAIN_DOWN = "I couldn't reach my music brain just now. Try again in a moment."
NOTHING_TO_UNDO = "There's nothing to undo yet."
NOTHING_TO_REDO = "There's nothing to redo."
UNDONE, REDONE = "Okay, back to how it was.", "Okay, brought that back."
FALLBACK = {
    "clarify": "Which part do you mean?",
    "unsupported": "I can't do that one, but I can change the genre, mood, tempo, key, instruments or mix.",
    "off_topic": "I'm all about your song. Want to try a different genre?",
    "unclear": NOTHING_TYPED,
}


@dataclass
class ChatTurn:
    heard: str
    intent: str  # edit | undo | redo | clarify | unsupported | off_topic | unclear | busy | error
    reply: str
    project: Project | None = None  # the edited project, when the song changed
    changed: list[str] = field(default_factory=list)  # tracks to render again
    mixed: list[str] = field(default_factory=list)  # tracks whose mixer settings changed
    label: str = ""  # what changed, for the undo history ("drums quieter")
    timings: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "heard": self.heard, "intent": self.intent, "reply": self.reply,
            "project": self.project.to_json() if self.project else None,
            "changed": self.changed, "mixed": self.mixed, "label": self.label,
            "timings": self.timings, "error": self.error,
        }


class ChatPipeline:
    def __init__(self, understand: Understand, transcribe: Transcribe | None = None):
        self._understand = understand
        self._transcribe = transcribe

    def from_text(self, text: str, project: Project, can_undo: bool = True, can_redo: bool = True) -> ChatTurn:
        started = time.perf_counter()
        return _timed(self._interpret((text or "").strip(), project, can_undo, can_redo), {}, started)

    def from_audio(self, audio: bytes, filename: str, project: Project, can_undo: bool = True,
                   can_redo: bool = True) -> ChatTurn:
        started = time.perf_counter()
        try:
            heard = self._transcribe(audio, filename)
        except MissingKey as exc:
            return _timed(ChatTurn("", "error", str(exc), error=str(exc)), {}, started)
        except Exception as exc:  # noqa: BLE001 - said kindly; the app falls back to typing
            log.exception("speech to text failed")
            return _timed(ChatTurn("", "error", EARS_FAILED, error=_described(exc)), {}, started)
        timings = {"transcribe_ms": _ms_since(started)}
        if not heard:
            return _timed(ChatTurn("", "unclear", NOTHING_HEARD), timings, started)
        return _timed(self._interpret(heard, project, can_undo, can_redo), timings, started)

    def _interpret(self, text: str, project: Project, can_undo: bool, can_redo: bool) -> ChatTurn:
        if not text:
            return ChatTurn("", "unclear", NOTHING_TYPED)
        try:
            answer = self._understand(text, project)
        except GeminiBusy as exc:
            log.warning("gemini rate limited: %s", exc)
            return ChatTurn(text, "busy", BUSY, error=str(exc)[:300])
        except MissingKey as exc:
            return ChatTurn(text, "error", str(exc), error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("understanding failed")
            return ChatTurn(text, "error", BRAIN_DOWN, error=_described(exc))
        return _decide(text, answer, project, can_undo, can_redo)


def _decide(text: str, answer: Answer, project: Project, can_undo: bool, can_redo: bool) -> ChatTurn:
    if answer.intent == "undo":
        return ChatTurn(text, "undo", (answer.reply or UNDONE) if can_undo else NOTHING_TO_UNDO)
    if answer.intent == "redo":
        return ChatTurn(text, "redo", (answer.reply or REDONE) if can_redo else NOTHING_TO_REDO)
    if answer.intent != "edit" or not answer.edits:
        intent = answer.intent if answer.intent != "edit" else "unclear"
        return ChatTurn(text, intent, answer.reply or FALLBACK[intent])
    result = apply(project, answer.edits)
    if not result.done:
        return ChatTurn(text, "edit", " ".join(result.refused) or "That's already how it is.")
    if result.refused:  # Gemini's sentence described edits that weren't all made
        reply = f"Done: {result.label}. {result.refused[0]}"
    else:
        reply = answer.reply or f"Done: {result.label}."
    return ChatTurn(text, "edit", reply, result.project, result.changed, result.mixed, result.label)


def _timed(turn: ChatTurn, timings: dict, started: float) -> ChatTurn:
    turn.timings = {**timings, "total_ms": _ms_since(started)}
    return turn


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _described(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]
