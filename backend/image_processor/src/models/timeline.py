"""Final export shape (Phase 9/10) - matches the notes.json schema."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NoteEvent:
    id: int
    hz: float
    start: float
    duration: float
    dynamic: float
    measure: Optional[int] = None
    beat: Optional[float] = None
    voice: Optional[int] = None

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "data": {
                "hz": self.hz,
                "start": self.start,
                "duration": self.duration,
                "dynamic": self.dynamic,
            },
        }
