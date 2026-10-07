"""Changes a listener asks for on top of a style (the app's faders and talk mode), in the
arrangement's own terms: tempo, transposition, major/minor, instruments, energy.

The arrangement doesn't know the app's words ("a bit faster", "add a cello"); whoever calls it
turns them into these numbers (routes/pipeline.py does it for the app).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SECTIONS = ("all", "start", "end")
KINDS = ("chords", "bass", "drums")


@dataclass(frozen=True)
class ExtraPart:
    """One more instrument under the style's orchestra."""

    program: int  # General MIDI program (ignored for drums)
    kind: str = "chords"  # "chords" (held chords), "bass" (a bass line) or "drums" (a backbeat)
    volume: int = 70  # MIDI channel volume, 0-127
    section: str = "all"  # where it plays: "all", "start" (first half) or "end" (second half)

    def __post_init__(self):
        if self.kind not in KINDS or self.section not in SECTIONS:
            raise ValueError(f"Bad part: {self}")
        if not 0 <= self.program <= 127 or not 0 <= self.volume <= 127:
            raise ValueError(f"Bad part: {self}")


@dataclass(frozen=True)
class ArrangeSettings:
    tempo_scale: float = 1.0  # the melody's tempo times this (0.5 = half speed)
    transpose: int = 0  # semitones, -12 to 12; the key moves with it
    mode: str | None = None  # "major" or "minor": the tune moves into that mode; None keeps it
    lead: int | None = None  # General MIDI program for the melody; None: the style's own
    lead_volume: int | None = None  # MIDI channel volume for the melody; None: the style's
    parts: tuple[ExtraPart, ...] = field(default_factory=tuple)
    energy: tuple[int, int] = (0, 0)  # the first and second half: -2 (calmest) to 2 (biggest)
    ensemble: str | None = None  # who plays: "orchestra", "band", "electronic", "chamber" (ensembles.py)
    variation: int | None = None  # a seed: picks the ensemble (if none is named) and its instruments

    def __post_init__(self):
        if not 0.25 <= self.tempo_scale <= 2.0:
            raise ValueError("tempo_scale must be between 0.25 and 2.")
        if not -12 <= self.transpose <= 12:
            raise ValueError("transpose must be between -12 and 12 semitones.")
        if self.mode not in (None, "major", "minor"):
            raise ValueError("mode must be major, minor or None.")
        if self.lead is not None and not 0 <= self.lead <= 127:
            raise ValueError("lead must be a MIDI program, 0-127.")
        if not all(-2 <= e <= 2 for e in self.energy):
            raise ValueError("energy must be between -2 and 2.")
        if self.ensemble is not None:
            from .ensembles import ENSEMBLES

            if self.ensemble not in ENSEMBLES:
                raise ValueError(f"Unknown ensemble {self.ensemble!r}; choose one of {', '.join(sorted(ENSEMBLES))}.")

    @property
    def is_default(self) -> bool:
        return self == ArrangeSettings()

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = ArrangeSettings()
ENERGY_STEP = 0.2  # each step of energy plays that half this much harder (or softer)
