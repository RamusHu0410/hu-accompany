"""Shared data shapes carried through every phase of the pipeline.

These exist so later phases (2-10, currently stubbed) have a stable contract
to type against even before real detection/classification logic lands.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BoundingBox:
    """Pixel-space box on a rendered page image. x/y are top-left."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class ConfidenceRecord:
    """One stage's confidence contribution to an object. Never overwritten -
    each stage appends its own record so the full history is inspectable."""

    stage: str
    value: float
    reason: str = ""


@dataclass
class MusicObject:
    """A single detected/classified musical object, traceable back to a
    pixel region on a specific page. Populated starting in Phase 2."""

    id: int
    page: int
    bbox: BoundingBox
    staff: Optional[int] = None
    crop_path: Optional[str] = None
    primary_label: Optional[str] = None
    candidate_labels: list = field(default_factory=list)
    ocr_text: Optional[str] = None
    confidence_history: list = field(default_factory=list)

    def final_confidence(self) -> float:
        if not self.confidence_history:
            return 0.0
        return self.confidence_history[-1].value
