"""Plain dataclasses shared across the imslp package.

These describe shapes moving between search -> parser -> normalizer -> service.
They are intentionally framework-free (no Django/Pydantic) so the imslp package
has no dependency on how the API layer serializes its output.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchHit:
    title: str
    composer: str
    url: str


@dataclass
class Edition:
    editor: Optional[str] = None
    publisher: Optional[str] = None
    copyright: Optional[str] = None
    scanner: Optional[str] = None
    date_submitted: Optional[str] = None
    misc_notes: Optional[str] = None
    file_description: Optional[str] = None
    file_names: list = field(default_factory=list)


@dataclass
class RawSection:
    """A single instrumentation/version section scraped from a work page,
    before normalization."""

    category: str  # "score" | "arrangement"
    movement: Optional[str]
    instrumentation_label: Optional[str]
    editions: list  # list[Edition]


@dataclass
class Choice:
    id: str
    name: str
    instrumentation: str
    type: str  # "Original Score" | "Arrangement"
    imslp_url: str
    movement: Optional[str] = None
    arranger: Optional[str] = None
    editor: Optional[str] = None
    file_name: Optional[str] = None  # original filename on IMSLP, e.g. "...pdf"


@dataclass
class WorkResult:
    title: str
    composer: str
    imslp_url: str
    choices: list  # list[Choice]
