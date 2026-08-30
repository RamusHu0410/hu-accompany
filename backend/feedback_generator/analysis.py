"""Objective, numeric comparison of a user's phrase against the expected
notes: error detection and 0-100 score computation. No natural-language
strings are built here -- that's nlg.py's job (see orchestrator.py for how
the two layers are wired together).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .alignment import AlignmentResult
from .models import ExpectedNote, ScoreBreakdown, UserNote
from .pitch_utils import hz_to_cents

# Anything within this many cents (1/100th of a semitone) is normal
# intonation/performance variance, not an error. Wider than the retired
# archive/scripts/rating.py prototype's flat CENTS_TOLERANCE=10.0, since
# that compared exact synthetic fixtures rather than live human playing.
CENTS_INSIGNIFICANT = 25.0
CENTS_MINOR = 50.0  # at/above this, effectively a different note ("wrong pitch")

TIMING_MINOR_FRACTION_OF_BEAT = 0.10
TIMING_MAJOR_FRACTION_OF_BEAT = 0.25
TIMING_MINOR_FLOOR_MS = 15.0
TIMING_MAJOR_FLOOR_MS = 40.0

DURATION_MINOR_PCT = 0.15  # |user_dur - expected_dur| / expected_dur
DURATION_MAJOR_PCT = 0.35
DURATION_FLOOR_MS = 20.0

ARTICULATION_STACCATO_MAX_RATIO = 0.6  # played_duration / expected_duration
ARTICULATION_LEGATO_MIN_RATIO = 0.85
ARTICULATION_WORDS = {"staccato", "legato", "marcato"}

OVERALL_WEIGHTS = {"pitch": 0.30, "rhythm": 0.25, "tempo": 0.20, "articulation": 0.15, "dynamics": 0.10}


@dataclass
class NoteError:
    note_id: Optional[int]
    category: str  # "pitch" | "timing" | "duration" | "missing_note" | "extra_note" | "articulation"
    severity: str  # "minor" | "major"
    expected: Optional[ExpectedNote]
    user: Optional[UserNote]
    detail: dict


@dataclass
class TempoDrift:
    insufficient_data: bool
    significant: bool
    direction: Optional[str]  # "slowing" | "rushing"
    drift_ms: float


@dataclass
class PhraseAnalysis:
    alignment: AlignmentResult
    errors: List[NoteError]
    tempo_drift: TempoDrift
    scores: ScoreBreakdown


def _effective_threshold_ms(fraction_of_beat: float, floor_ms: float, beat_ms: float) -> float:
    return max(fraction_of_beat * beat_ms, floor_ms)


def _score_falloff(value_abs: float, insignificant: float, cap: float) -> float:
    """100 at/below `insignificant`, smoothly down to 0 at/above `cap`."""
    if value_abs <= insignificant:
        return 100.0
    if value_abs >= cap:
        return 0.0
    return 100.0 * (1 - (value_abs - insignificant) / (cap - insignificant))


def _articulation_marking(expected: ExpectedNote) -> Optional[str]:
    if not expected.markings:
        return None
    lowered = expected.markings.lower()
    for word in ARTICULATION_WORDS:
        if word in lowered:
            return word
    return None


# --- Error detection (matched notes) ----------------------------------------

def detect_pitch_error(expected: ExpectedNote, user: UserNote) -> Optional[NoteError]:
    cents = hz_to_cents(user.pitch_hz, expected.pitch_hz)
    cents_abs = abs(cents)
    if cents_abs < CENTS_INSIGNIFICANT:
        return None
    severity = "major" if cents_abs >= CENTS_MINOR else "minor"
    return NoteError(
        note_id=expected.note_id,
        category="pitch",
        severity=severity,
        expected=expected,
        user=user,
        detail={"cents": cents, "user_hz": user.pitch_hz, "expected_hz": expected.pitch_hz},
    )


def detect_timing_error(expected: ExpectedNote, user: UserNote, bpm: float) -> Optional[NoteError]:
    beat_ms = 60000.0 / bpm
    diff_ms = user.start_time_ms - expected.start_time_ms
    diff_abs = abs(diff_ms)
    minor_threshold = _effective_threshold_ms(TIMING_MINOR_FRACTION_OF_BEAT, TIMING_MINOR_FLOOR_MS, beat_ms)
    major_threshold = _effective_threshold_ms(TIMING_MAJOR_FRACTION_OF_BEAT, TIMING_MAJOR_FLOOR_MS, beat_ms)
    if diff_abs < minor_threshold:
        return None
    severity = "major" if diff_abs >= major_threshold else "minor"
    return NoteError(
        note_id=expected.note_id,
        category="timing",
        severity=severity,
        expected=expected,
        user=user,
        detail={"diff_ms": diff_ms, "direction": "late" if diff_ms > 0 else "early"},
    )


def detect_duration_error(expected: ExpectedNote, user: UserNote) -> Optional[NoteError]:
    if expected.duration_ms <= 0:
        return None
    diff_ms = user.duration_ms - expected.duration_ms
    diff_abs = abs(diff_ms)
    minor_threshold = max(DURATION_FLOOR_MS, DURATION_MINOR_PCT * expected.duration_ms)
    major_threshold = max(DURATION_FLOOR_MS, DURATION_MAJOR_PCT * expected.duration_ms)
    if diff_abs < minor_threshold:
        return None
    severity = "major" if diff_abs >= major_threshold else "minor"
    return NoteError(
        note_id=expected.note_id,
        category="duration",
        severity=severity,
        expected=expected,
        user=user,
        detail={"diff_ms": diff_ms, "pct": diff_abs / expected.duration_ms, "direction": "too_long" if diff_ms > 0 else "too_short"},
    )


def detect_articulation_error(expected: ExpectedNote, user: UserNote) -> Optional[NoteError]:
    marking = _articulation_marking(expected)
    if marking is None or expected.duration_ms <= 0:
        return None
    ratio = user.duration_ms / expected.duration_ms

    if marking == "staccato":
        if ratio <= ARTICULATION_STACCATO_MAX_RATIO:
            return None
        severity = "major" if ratio > ARTICULATION_STACCATO_MAX_RATIO * 1.5 else "minor"
    else:  # legato / marcato: played too short
        if ratio >= ARTICULATION_LEGATO_MIN_RATIO:
            return None
        severity = "major" if ratio < ARTICULATION_LEGATO_MIN_RATIO * 0.7 else "minor"

    return NoteError(
        note_id=expected.note_id,
        category="articulation",
        severity=severity,
        expected=expected,
        user=user,
        detail={"marking": marking, "ratio": ratio},
    )


def build_missing_error(expected: ExpectedNote) -> NoteError:
    return NoteError(
        note_id=expected.note_id,
        category="missing_note",
        severity="major",
        expected=expected,
        user=None,
        detail={"expected_hz": expected.pitch_hz},
    )


def build_extra_error(user: UserNote) -> NoteError:
    return NoteError(
        note_id=user.note_id,
        category="extra_note",
        severity="major",
        expected=None,
        user=user,
        detail={"user_hz": user.pitch_hz},
    )


def detect_errors(alignment: AlignmentResult, bpm: float) -> List[NoteError]:
    errors: List[NoteError] = []
    for expected, user in alignment.matched:
        for error in (
            detect_pitch_error(expected, user),
            detect_timing_error(expected, user, bpm),
            detect_duration_error(expected, user),
            detect_articulation_error(expected, user),
        ):
            if error is not None:
                errors.append(error)
    errors.extend(build_missing_error(expected) for expected in alignment.missing)
    errors.extend(build_extra_error(user) for user in alignment.extra)
    errors.sort(key=lambda e: e.expected.start_time_ms if e.expected is not None else e.user.start_time_ms)
    return errors


# --- Phrase-level tempo drift -------------------------------------------------

MIN_MATCHED_NOTES_FOR_TEMPO_TREND = 4


def detect_tempo_drift(alignment: AlignmentResult, bpm: float) -> TempoDrift:
    matched = sorted(alignment.matched, key=lambda pair: pair[0].start_time_ms)
    if len(matched) < MIN_MATCHED_NOTES_FOR_TEMPO_TREND:
        return TempoDrift(insufficient_data=True, significant=False, direction=None, drift_ms=0.0)

    def mean_offset(pairs: List[Tuple[ExpectedNote, UserNote]]) -> float:
        offsets = [user.start_time_ms - expected.start_time_ms for expected, user in pairs]
        return sum(offsets) / len(offsets)

    mid = len(matched) // 2
    first_offset = mean_offset(matched[:mid])
    second_offset = mean_offset(matched[mid:])
    drift_ms = second_offset - first_offset

    beat_ms = 60000.0 / bpm
    threshold = _effective_threshold_ms(TIMING_MINOR_FRACTION_OF_BEAT, TIMING_MINOR_FLOOR_MS, beat_ms)
    significant = abs(drift_ms) >= threshold
    direction = ("slowing" if drift_ms > 0 else "rushing") if significant else None
    return TempoDrift(insufficient_data=False, significant=significant, direction=direction, drift_ms=drift_ms)


# --- Score computation --------------------------------------------------------

def _pitch_note_score(expected: ExpectedNote, user: UserNote) -> float:
    cents_abs = abs(hz_to_cents(user.pitch_hz, expected.pitch_hz))
    return _score_falloff(cents_abs, CENTS_INSIGNIFICANT, 200.0)


def _rhythm_note_score(expected: ExpectedNote, user: UserNote, bpm: float) -> float:
    beat_ms = 60000.0 / bpm
    onset_diff = abs(user.start_time_ms - expected.start_time_ms)
    onset_minor = _effective_threshold_ms(TIMING_MINOR_FRACTION_OF_BEAT, TIMING_MINOR_FLOOR_MS, beat_ms)
    onset_major = _effective_threshold_ms(TIMING_MAJOR_FRACTION_OF_BEAT, TIMING_MAJOR_FLOOR_MS, beat_ms)
    onset_score = _score_falloff(onset_diff, onset_minor, onset_major * 2)

    duration_diff = abs(user.duration_ms - expected.duration_ms)
    duration_minor = max(DURATION_FLOOR_MS, DURATION_MINOR_PCT * expected.duration_ms) if expected.duration_ms else DURATION_FLOOR_MS
    duration_major = max(DURATION_FLOOR_MS, DURATION_MAJOR_PCT * expected.duration_ms) if expected.duration_ms else DURATION_FLOOR_MS
    duration_score = _score_falloff(duration_diff, duration_minor, duration_major * 2)

    return (onset_score + duration_score) / 2


def compute_pitch_score(alignment: AlignmentResult) -> Optional[int]:
    total = len(alignment.matched) + len(alignment.missing)
    if total == 0:
        return None
    matched_total = sum(_pitch_note_score(expected, user) for expected, user in alignment.matched)
    return round(matched_total / total)  # missing notes contribute 0


def compute_rhythm_score(alignment: AlignmentResult, bpm: float) -> Optional[int]:
    total = len(alignment.matched) + len(alignment.missing)
    if total == 0:
        return None
    matched_total = sum(_rhythm_note_score(expected, user, bpm) for expected, user in alignment.matched)
    return round(matched_total / total)  # missing notes contribute 0


def compute_tempo_score(tempo_drift: TempoDrift, bpm: float) -> Optional[int]:
    if tempo_drift.insufficient_data:
        return None
    beat_ms = 60000.0 / bpm
    minor_threshold = _effective_threshold_ms(TIMING_MINOR_FRACTION_OF_BEAT, TIMING_MINOR_FLOOR_MS, beat_ms)
    major_threshold = _effective_threshold_ms(TIMING_MAJOR_FRACTION_OF_BEAT, TIMING_MAJOR_FLOOR_MS, beat_ms)
    return round(_score_falloff(abs(tempo_drift.drift_ms), minor_threshold, major_threshold * 2))


def compute_dynamics_score(alignment: AlignmentResult) -> Optional[int]:
    """Always None: no note schema anywhere upstream (mobile app / native_ffi)
    currently carries a loudness/velocity value, so a real dynamics score
    cannot be computed without fabricating one. See feedback_generator/README.md.
    """
    return None


def _articulation_note_score(marking: str, ratio: float) -> float:
    if marking == "staccato":
        return 100.0 if ratio <= ARTICULATION_STACCATO_MAX_RATIO else _score_falloff(ratio, ARTICULATION_STACCATO_MAX_RATIO, 1.0)
    # legato / marcato: shorter than expected is the problem
    if ratio >= ARTICULATION_LEGATO_MIN_RATIO:
        return 100.0
    badness = ARTICULATION_LEGATO_MIN_RATIO - ratio
    return _score_falloff(badness, 0.0, ARTICULATION_LEGATO_MIN_RATIO)


def compute_articulation_score(alignment: AlignmentResult) -> Optional[int]:
    scored = []
    for expected, user in alignment.matched:
        marking = _articulation_marking(expected)
        if marking is None or expected.duration_ms <= 0:
            continue
        scored.append(_articulation_note_score(marking, user.duration_ms / expected.duration_ms))
    if not scored:
        return None
    return round(sum(scored) / len(scored))


def compute_overall_score(component_scores: Dict[str, Optional[int]]) -> Optional[int]:
    available = {category: score for category, score in component_scores.items() if score is not None}
    if not available:
        return None
    total_weight = sum(OVERALL_WEIGHTS[category] for category in available)
    weighted_sum = sum(OVERALL_WEIGHTS[category] * score for category, score in available.items())
    return round(weighted_sum / total_weight)


def compute_scores(alignment: AlignmentResult, tempo_drift: TempoDrift, bpm: float) -> ScoreBreakdown:
    pitch = compute_pitch_score(alignment)
    rhythm = compute_rhythm_score(alignment, bpm)
    tempo = compute_tempo_score(tempo_drift, bpm)
    dynamics = compute_dynamics_score(alignment)
    articulation = compute_articulation_score(alignment)
    overall = compute_overall_score(
        {"pitch": pitch, "rhythm": rhythm, "tempo": tempo, "dynamics": dynamics, "articulation": articulation}
    )
    return ScoreBreakdown(
        overall=overall, pitch=pitch, rhythm=rhythm, tempo=tempo, dynamics=dynamics, articulation=articulation
    )


def analyze_phrase(alignment: AlignmentResult, bpm: float) -> PhraseAnalysis:
    errors = detect_errors(alignment, bpm)
    tempo_drift = detect_tempo_drift(alignment, bpm)
    scores = compute_scores(alignment, tempo_drift, bpm)
    return PhraseAnalysis(alignment=alignment, errors=errors, tempo_drift=tempo_drift, scores=scores)
