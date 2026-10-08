"""Melody data models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Note:
    """A single note.

    Attributes:
        hz: Frequency of the note in hertz.
        start: Start time of the note in seconds (or beats).
        duration: Length of the note in seconds (or beats).
    """

    hz: float
    start: float
    duration: float

    def __repr__(self) -> str:
        return f"hz={self.hz} start={self.start} duration={self.duration}"


@dataclass
class Melody:
    """A melody: an ordered collection of notes with musical context.

    Attributes:
        notes: The notes that make up the melody.
        key: The tonal key (e.g. "C", "A#").
        mode: The mode (e.g. "major", "minor").
        tempo: Tempo in beats per minute.
    """

    notes: list[Note] = field(default_factory=list)
    key: str = "C"
    mode: str = "major"
    tempo: float = 120.0

    @classmethod
    def from_dict(cls, data: dict) -> "Melody":
        """Build a Melody from a JSON-style dict.

        Expects a "melody" list of note dicts (hz/start/duration) plus
        optional "key", "mode", and "tempo" fields.

        Raises:
            ValueError: a note or the tempo isn't usable (the message names which
                one and why), so API callers get a 400 rather than a crash.
        """
        raw_notes = data.get("melody", [])
        if not isinstance(raw_notes, list):
            raise ValueError("'melody' must be a list of notes.")
        notes = [_note_from_dict(i, n) for i, n in enumerate(raw_notes)]
        tempo = data.get("tempo")
        tempo = 120.0 if tempo is None else _number(tempo, "tempo")
        if not 0 < tempo <= 400:
            raise ValueError(f"tempo must be between 0 and 400 BPM, got {tempo}.")
        return cls(
            notes=notes,
            key=data.get("key") or "C",
            mode=data.get("mode") or "major",
            tempo=tempo,
        )


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}.")
    return float(value)


def _note_from_dict(index: int, data) -> Note:
    """One note, checked: hz (a MIDI note number) in 0-127, start >= 0, duration > 0."""
    if not isinstance(data, dict) or not {"hz", "start", "duration"} <= data.keys():
        raise ValueError(f"melody[{index}] must have hz, start and duration.")
    hz = _number(data["hz"], f"melody[{index}].hz")
    start = _number(data["start"], f"melody[{index}].start")
    duration = _number(data["duration"], f"melody[{index}].duration")
    if not 0 <= hz <= 127:
        raise ValueError(f"melody[{index}].hz is a MIDI note number (0-127), got {hz}.")
    if start < 0:
        raise ValueError(f"melody[{index}].start can't be negative, got {start}.")
    if duration <= 0:
        raise ValueError(f"melody[{index}].duration must be positive, got {duration}.")
    return Note(hz=data["hz"], start=data["start"], duration=data["duration"])
