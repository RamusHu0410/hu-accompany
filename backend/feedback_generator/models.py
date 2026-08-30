"""Plain dataclasses shared across the feedback_generator package.

These describe shapes moving between alignment -> analysis -> nlg -> orchestrator.
They are intentionally framework-free (no Django/Pydantic) so this package has
no dependency on how the API layer serializes its output.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExpectedNote:
    """A single note from the expected-performance data (same shape as
    pdf_processor's piece_data notes / native_ffi's Notes struct)."""

    note_id: int
    pitch_hz: float
    start_time_ms: float
    end_time_ms: float
    duration_ms: float
    vibrato_depth: Optional[float] = None
    pedal_action: Optional[str] = None
    has_accent: Optional[bool] = None
    markings: Optional[str] = None


@dataclass
class UserNote:
    """A single note detected from the user's recording of the phrase."""

    pitch_hz: float
    start_time_ms: float
    end_time_ms: float
    duration_ms: float
    note_id: Optional[int] = None
    has_accent: Optional[bool] = None


@dataclass
class ImmediateFeedbackItem:
    note_id: Optional[int]
    category: str
    severity: str
    message: str
    suggestion: str
    type: str = "immediate"


@dataclass
class MainFeedbackItem:
    category: str
    severity: str
    description: str
    practice_action: str


@dataclass
class ScoreBreakdown:
    overall: Optional[int]
    pitch: Optional[int]
    rhythm: Optional[int]
    tempo: Optional[int]
    dynamics: Optional[int]
    articulation: Optional[int]


@dataclass
class PhraseSummary:
    phrase: int
    scores: ScoreBreakdown
    summary: str
    main_feedback: list = field(default_factory=list)
    positive_feedback: list = field(default_factory=list)
    type: str = "phrase_summary"


@dataclass
class PhraseFeedbackResult:
    phrase: int
    immediate_feedback: list
    phrase_summary: PhraseSummary
