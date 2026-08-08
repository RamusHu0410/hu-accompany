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
    # Detector-specific extras that don't fit the generic shape above (e.g.
    # oemer's group/track/stem-direction/accidental). Keyed by "kind" =
    # "note" | "rest" | "clef" | "accidental" so consumers can tell object
    # types apart without a separate class per kind.
    attributes: dict = field(default_factory=dict)

    def final_confidence(self) -> float:
        if not self.confidence_history:
            return 0.0
        return self.confidence_history[-1].value


@dataclass
class PageDetection:
    """Phase 2 output for one page.

    Bboxes on `objects` and `barlines` are in oemer's resized/dewarped
    coordinate space (`image_size`), NOT the original page pixel space from
    Phase 1 - oemer downsamples internally regardless of input resolution.
    `image_path` is oemer's own rendering of that space, saved so later
    phases (and debugging) can line bboxes up against actual pixels.
    """

    page: int
    image_path: Optional[str] = None
    image_size: Optional[tuple] = None  # (width, height)
    objects: list = field(default_factory=list)  # list[MusicObject]
    barlines: list = field(default_factory=list)  # list[BoundingBox]
    musicxml_path: Optional[str] = None  # oemer's builder output, one self-contained
    # document per page (its own measure 1) - Phase 5 stitches these together.
    error: Optional[str] = None
