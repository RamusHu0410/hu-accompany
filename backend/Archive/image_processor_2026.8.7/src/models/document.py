"""Phase 1 (Document Preparation) output shapes."""

from dataclasses import dataclass, field
from typing import Optional

from .objects import BoundingBox


@dataclass
class DocumentMetadata:
    source_path: str
    page_count: int
    title: str = ""
    author: str = ""
    producer: str = ""


@dataclass
class StaffRegion:
    """One detected staff system on a page."""

    bbox: BoundingBox
    line_spacing_px: float
    confidence: float


@dataclass
class PageInfo:
    page_number: int  # 1-indexed
    render_path: str
    width: int
    height: int
    rotation_deg: float = 0.0
    corrected_render_path: Optional[str] = None
    content_bbox: Optional[BoundingBox] = None
    staff_regions: list = field(default_factory=list)  # list[StaffRegion]


@dataclass
class PageError:
    page_number: int
    stage: str
    message: str


@dataclass
class DocumentPreparation:
    metadata: DocumentMetadata
    pages: list  # list[PageInfo], successfully processed pages only
    page_errors: list = field(default_factory=list)  # list[PageError]
