"""Chord data model."""

from __future__ import annotations

from dataclasses import dataclass

# Short symbol suffixes per quality, used for a compact chord label (e.g. "Dm").
_QUALITY_SUFFIX = {
    "major": "",
    "minor": "m",
    "diminished": "dim",
    "augmented": "aug",
}


@dataclass
class Chord:
    """A chord placed on a timeline.

    Attributes:
        root: Root note name (e.g. "C", "F#", "Bb").
        quality: Chord quality ("major", "minor", "diminished", "augmented").
        start: Onset time (in the melody's time units).
        duration: Length of the chord.
    """

    root: str
    quality: str
    start: float = 0.0
    duration: float = 2.0

    @property
    def symbol(self) -> str:
        """Compact chord symbol, e.g. 'C', 'Dm', 'Bdim'."""
        return self.root + _QUALITY_SUFFIX.get(self.quality, self.quality)

    def __repr__(self) -> str:
        return self.symbol
