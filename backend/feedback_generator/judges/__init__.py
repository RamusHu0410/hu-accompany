"""Judges: one module per feedback dimension.

Every judge owns one slice of the assessment -- its own error detection, its
own 0-100 rating, and its own prose. Nothing outside `judges/` writes
feedback text; orchestrator.py only wires judges together and summarizer.py
only aggregates what they produced.

Judges are split by when they run:

    phase1/  one submitted phrase at a time -- receives a PhraseContext
    phase2/  the whole session at once      -- receives a PieceContext

Judge contract, the same in both:

    NAME  : str   -- the finding category this judge emits
    PHASE : 1 | 2
    judge(ctx) -> JudgeResult

Each sub-package's __init__ lists its judges in JUDGES; phase1_judges() and
phase2_judges() below are what orchestrator.py runs.

This module holds only what judges of both phases share: the
note/context/finding dataclasses, pitch and timing math,
threshold-to-severity mapping, and the registry. It is deliberately
framework-free (no Django/Pydantic) so the package doesn't depend on how the
API layer serializes its output.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- Notes -------------------------------------------------------------------


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


# --- Judge input / output -----------------------------------------------------


@dataclass
class Finding:
    """One piece of feedback, and the unit every stored JSON file is a list
    of. `bars` is the 1-based bar the finding sits in (piece-level findings
    use 0). `confidence` is 0.0-1.0: how far past the "this is an error"
    threshold the measurement is, so a borderline miss reads differently
    from an unmistakable one.
    """

    bars: int
    category: str
    severity: str  # "minor" | "major" (phase-2 style notes may use "info")
    confidence: float
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class JudgeResult:
    """What one judge produced for one phrase (or for the whole piece).
    `score` is None when this judge had nothing to measure -- e.g. a phrase
    with no articulation markings -- and is then left out of the overall.
    `details` carries judge-specific extras that aren't per-bar findings
    (era.py's era/label/traits).
    """

    category: str
    score: Optional[int]
    findings: List[Finding] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class PhraseContext:
    """One phrase's user notes already aligned to its expected notes by
    orchestrator.py. Every phase-1 judge reads the same context."""

    phrase: int
    bpm: float
    beats_per_bar: float
    matched: List[Tuple[ExpectedNote, UserNote]]
    missing: List[ExpectedNote]
    extra: List[UserNote]

    @property
    def beat_ms(self) -> float:
        return 60000.0 / self.bpm

    def bar(self, start_time_ms: float) -> int:
        return bar_of(start_time_ms, self.bpm, self.beats_per_bar)


@dataclass
class PieceContext:
    """Everything phase 2 gets: the piece metadata, every stored phase-1
    phrase file (in phrase order), the per-dimension scores aggregated
    across them, and every phase-1 finding flattened into one list."""

    piece: dict = field(default_factory=dict)
    phrases: List[dict] = field(default_factory=list)
    scores: Dict[str, Optional[int]] = field(default_factory=dict)
    findings: List[dict] = field(default_factory=list)


# --- Pitch math ---------------------------------------------------------------

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
A4_HZ = 440.0
A4_MIDI = 69


def hz_to_cents(user_hz: float, expected_hz: float) -> float:
    """Signed distance in cents (1/100th of a semitone) from expected_hz to
    user_hz. Positive = user played sharp/higher than expected."""
    return 1200 * math.log2(user_hz / expected_hz)


def hz_to_midi(hz: float) -> float:
    return A4_MIDI + 12 * math.log2(hz / A4_HZ)


def hz_to_note_name(hz: float) -> str:
    """Nearest note name (e.g. "F#4") for a frequency, rounded to the nearest semitone."""
    midi = round(hz_to_midi(hz))
    name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"


# --- Bar math -----------------------------------------------------------------

DEFAULT_TIME_SIGNATURE = "4/4"


def beats_per_bar(time_signature: Optional[str]) -> float:
    """Quarter-note beats per bar for a "n/d" time signature, since `bpm`
    everywhere upstream (pdf_processor, the app's metronome) counts quarter
    notes: 4/4 -> 4, 3/4 -> 3, 6/8 -> 3. Falls back to 4 on anything
    unparseable."""
    text = str(time_signature or DEFAULT_TIME_SIGNATURE)
    try:
        numerator, denominator = text.split("/")
        value = int(numerator) * (4.0 / int(denominator))
    except (ValueError, ZeroDivisionError):
        return 4.0
    return value if value > 0 else 4.0


def bar_of(start_time_ms: float, bpm: float, per_bar: float) -> int:
    """1-based bar number for a timestamp measured from the start of the piece."""
    bar_ms = (60000.0 / bpm) * per_bar
    if bar_ms <= 0:
        return 1
    return int(start_time_ms // bar_ms) + 1


def bar_span(bars) -> List[int]:
    """[first_bar, last_bar] over an iterable of bar numbers, or [] if there
    are none (0 = "no particular bar", so it doesn't count)."""
    numbered = [bar for bar in bars if bar]
    return [min(numbered), max(numbered)] if numbered else []


# --- Thresholds, severity, confidence, scores --------------------------------


def effective_threshold_ms(fraction_of_beat: float, floor_ms: float, beat_ms: float) -> float:
    """A tempo-relative threshold that never drops below `floor_ms` -- the
    same absolute slip matters more at 200bpm than at 60bpm."""
    return max(fraction_of_beat * beat_ms, floor_ms)


def severity_for(value_abs: float, minor: float, major: float) -> Optional[str]:
    """None below `minor` (normal human variance, not an error), else
    "minor"/"major"."""
    if value_abs < minor:
        return None
    return "major" if value_abs >= major else "minor"


def confidence_for(value_abs: float, minor: float, major: float) -> float:
    """0.5 right at the "this is an error" threshold, rising to 1.0 at twice
    the major threshold -- so a borderline call is reported as one."""
    if major <= minor:
        return 1.0
    ratio = (value_abs - minor) / (2 * major - minor)
    return round(min(1.0, max(0.0, 0.5 + 0.5 * ratio)), 2)


def score_falloff(value_abs: float, insignificant: float, cap: float) -> float:
    """100 at/below `insignificant`, smoothly down to 0 at/above `cap`."""
    if value_abs <= insignificant:
        return 100.0
    if value_abs >= cap:
        return 0.0
    return 100.0 * (1 - (value_abs - insignificant) / (cap - insignificant))


# How much each judge's rating counts towards the overall 0-100. Judges that
# scored None are dropped and the rest renormalized, so a phrase with no
# articulation markings isn't penalized for it.
OVERALL_WEIGHTS = {
    "pitch": 0.30,
    "rhythm": 0.25,
    "tempo": 0.20,
    "articulation": 0.15,
    "dynamics": 0.10,
}


def overall_score(scores: Dict[str, Optional[int]]) -> Optional[int]:
    available = {
        category: score
        for category, score in scores.items()
        if score is not None and category in OVERALL_WEIGHTS
    }
    if not available:
        return None
    total_weight = sum(OVERALL_WEIGHTS[category] for category in available)
    weighted_sum = sum(OVERALL_WEIGHTS[category] * score for category, score in available.items())
    return round(weighted_sum / total_weight)


# --- Registry -----------------------------------------------------------------
#
# Imported lazily: every judge module imports from this one, so importing
# them at module level here would be circular.


def phase1_judges() -> tuple:
    """Per-phrase judges, in the order their findings are listed."""
    from .phase1 import JUDGES

    return JUDGES


def phase2_judges() -> tuple:
    """Whole-piece judges -- run once, after every phrase has been judged."""
    from .phase2 import JUDGES

    return JUDGES
