"""Turns analysis.py's objective NoteError/score/tempo-drift data into the
human-readable message/suggestion/summary/practice_action strings the API
returns. This is the only module in feedback_generator that builds prose --
alignment.py and analysis.py deal strictly in numbers/enums/dataclasses.

Generation is deterministic/template-based (no LLM call): google-genai is a
backend dependency but its only current usage (imslp_search) is commented
out, so there's no existing pattern for calling it, and the spec's examples
read as templated sentences rather than free-form generation.
"""

from typing import List, Tuple

from .analysis import NoteError, TempoDrift, TIMING_MAJOR_FLOOR_MS, TIMING_MAJOR_FRACTION_OF_BEAT
from .models import ImmediateFeedbackItem, MainFeedbackItem, PhraseSummary, ScoreBreakdown
from .pitch_utils import hz_to_note_name

POSITIVE_SCORE_THRESHOLD = 90
MIN_WEIGHT_TO_SURFACE = 1.0
MAX_MAIN_FEEDBACK_ITEMS = 3

# How much a category's weight (frequency x severity) is scaled before
# ranking -- keeps repeated, musically-core problems (wrong notes, dropped
# notes) ahead of less critical ones (articulation nuance) even when raw
# counts are similar.
CATEGORY_IMPORTANCE = {
    "pitch": 1.2,
    "missing_note": 1.2,
    "timing": 1.1,
    "tempo_drift": 1.0,
    "duration": 0.9,
    "extra_note": 0.9,
    "articulation": 0.7,
}

# Which 0-100 score dimension(s) each error/main-feedback category reflects,
# used to avoid praising a dimension that's already been flagged as a problem.
CATEGORY_TO_SCORE_DIMENSION = {
    "pitch": {"pitch"},
    "timing": {"rhythm"},
    "duration": {"rhythm"},
    "missing_note": {"pitch", "rhythm"},
    "extra_note": {"pitch", "rhythm"},
    "articulation": {"articulation"},
    "tempo_drift": {"tempo"},
}

POSITIVE_TEMPLATES = {
    "pitch": "Pitch accuracy was strong.",
    "rhythm": "Rhythmic accuracy was strong.",
    "tempo": "Tempo stayed steady and consistent.",
    "dynamics": "Dynamics were well controlled.",
    "articulation": "Articulation matched the markings well.",
}


# --- Immediate feedback (one item per significant error, no aggregation) ----

def _pitch_message(error: NoteError) -> Tuple[str, str]:
    detail = error.detail
    user_name = hz_to_note_name(detail["user_hz"])
    expected_name = hz_to_note_name(detail["expected_hz"])
    if user_name == expected_name:
        direction = "sharp" if detail["cents"] > 0 else "flat"
        message = f"This note was played slightly {direction}."
    else:
        message = f"Wrong note — you played {user_name} instead of {expected_name}."
    return message, "Practice this transition slowly and focus on the correct note."


def _timing_message(error: NoteError) -> Tuple[str, str]:
    direction = error.detail["direction"]
    message = f"This note came in {direction}, disrupting the rhythm."
    return message, "Practice this passage with a metronome, focusing on landing the note exactly on the beat."


def _duration_message(error: NoteError) -> Tuple[str, str]:
    if error.detail["direction"] == "too_long":
        message = "This note was held longer than written."
    else:
        message = "This note was cut short compared to what's written."
    return message, "Slow down and count out this note's full written duration before returning to full tempo."


def _missing_message(error: NoteError) -> Tuple[str, str]:
    return "This note was not played.", "Go through this passage slowly, note-by-note, to make sure this note is included."


def _extra_message(error: NoteError) -> Tuple[str, str]:
    return "An extra note was played that isn't in the score.", "Review the written notes here closely and avoid adding notes that aren't written."


def _articulation_message(error: NoteError) -> Tuple[str, str]:
    marking = error.detail["marking"]
    if marking == "staccato":
        message = "This note was held too long for the marked staccato articulation."
    else:
        message = f"This note was cut short for the marked {marking} articulation."
    return message, f"Practice this note in isolation with the marked {marking} articulation before returning to full tempo."


_IMMEDIATE_MESSAGE_BUILDERS = {
    "pitch": _pitch_message,
    "timing": _timing_message,
    "duration": _duration_message,
    "missing_note": _missing_message,
    "extra_note": _extra_message,
    "articulation": _articulation_message,
}


def build_immediate_feedback(errors: List[NoteError]) -> List[ImmediateFeedbackItem]:
    items = []
    for error in errors:
        builder = _IMMEDIATE_MESSAGE_BUILDERS.get(error.category)
        if builder is None:
            continue
        message, suggestion = builder(error)
        items.append(
            ImmediateFeedbackItem(
                note_id=error.note_id,
                category=error.category,
                severity=error.severity,
                message=message,
                suggestion=suggestion,
            )
        )
    return items


# --- Phrase summary: top problems, positive notes, one-line summary ---------

def _category_feedback_item(category: str, errors: List[NoteError]) -> MainFeedbackItem:
    count = len(errors)
    severity = "major" if any(e.severity == "major" for e in errors) else "minor"
    plural = count != 1

    templates = {
        "pitch": (
            f"Pitch was inaccurate on {count} notes in this phrase." if plural else "One note's pitch was noticeably off.",
            "Isolate the affected note(s) and check them against the expected pitch before playing the phrase at full tempo.",
        ),
        "timing": (
            f"{count} notes were noticeably early or late." if plural else "One note's timing was noticeably off.",
            "Practice this phrase with a metronome, focusing on landing each note exactly on the beat.",
        ),
        "duration": (
            f"{count} notes were held for noticeably longer or shorter than written." if plural else "One note's length didn't match what was written.",
            "Slow the phrase down and count out each note's full written duration before speeding back up.",
        ),
        "missing_note": (
            f"{count} expected notes were not played." if plural else "One expected note was not played.",
            "Go through the phrase slowly note-by-note to make sure every note is played.",
        ),
        "extra_note": (
            f"{count} extra notes were played that weren't in the score." if plural else "An extra note was played that wasn't in the score.",
            "Review the written notes for this phrase closely and remove any notes that aren't written.",
        ),
        "articulation": (
            f"Articulation didn't match the marking on {count} notes." if plural else "One note's articulation didn't match the marking.",
            "Practice the marked articulation in isolation -- short and detached for staccato, smooth and connected for legato -- before playing the full phrase.",
        ),
    }
    description, practice_action = templates[category]
    return MainFeedbackItem(category=category, severity=severity, description=description, practice_action=practice_action)


def _tempo_drift_feedback_item(tempo_drift: TempoDrift, bpm: float) -> MainFeedbackItem:
    beat_ms = 60000.0 / bpm
    major_threshold = max(TIMING_MAJOR_FRACTION_OF_BEAT * beat_ms, TIMING_MAJOR_FLOOR_MS)
    severity = "major" if abs(tempo_drift.drift_ms) >= major_threshold else "minor"
    verb = "slows" if tempo_drift.direction == "slowing" else "rushes"
    return MainFeedbackItem(
        category="tempo",
        severity=severity,
        description=f"The tempo gradually {verb} across the phrase.",
        practice_action="Practice the phrase with a metronome, paying close attention to keeping a steady tempo through to the end.",
    )


def build_main_feedback(errors: List[NoteError], tempo_drift: TempoDrift, bpm: float) -> List[MainFeedbackItem]:
    groups: dict = {}
    for error in errors:
        groups.setdefault(error.category, []).append(error)

    weighted = []
    for category, group_errors in groups.items():
        weight = sum(2 if e.severity == "major" else 1 for e in group_errors) * CATEGORY_IMPORTANCE.get(category, 1.0)
        weighted.append((weight, _category_feedback_item(category, group_errors)))

    if tempo_drift.significant:
        weight = 2 * CATEGORY_IMPORTANCE["tempo_drift"]
        weighted.append((weight, _tempo_drift_feedback_item(tempo_drift, bpm)))

    weighted.sort(key=lambda pair: pair[0], reverse=True)
    return [item for weight, item in weighted if weight >= MIN_WEIGHT_TO_SURFACE][:MAX_MAIN_FEEDBACK_ITEMS]


def build_positive_feedback(scores: ScoreBreakdown, main_feedback: List[MainFeedbackItem]) -> List[str]:
    flagged_dimensions = set()
    for item in main_feedback:
        flagged_dimensions |= CATEGORY_TO_SCORE_DIMENSION.get(item.category, {item.category})

    candidates = []
    for dimension, template in POSITIVE_TEMPLATES.items():
        score = getattr(scores, dimension)
        if score is not None and score >= POSITIVE_SCORE_THRESHOLD and dimension not in flagged_dimensions:
            candidates.append((score, template))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [template for _, template in candidates[:2]]


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if text else text


def _strip_period(text: str) -> str:
    return text[:-1] if text.endswith(".") else text


def build_summary(main_feedback: List[MainFeedbackItem], positive_feedback: List[str]) -> str:
    if positive_feedback and main_feedback:
        positive_clause = _strip_period(positive_feedback[0])
        problem_clause = _lower_first(_strip_period(main_feedback[0].description))
        return f"{positive_clause}, but {problem_clause}."
    if positive_feedback:
        return f"{positive_feedback[0]} No significant issues were detected in this phrase."
    if main_feedback:
        return main_feedback[0].description
    return "No significant issues were detected in this phrase."


def build_phrase_summary(
    phrase: int, scores: ScoreBreakdown, errors: List[NoteError], tempo_drift: TempoDrift, bpm: float
) -> PhraseSummary:
    main_feedback = build_main_feedback(errors, tempo_drift, bpm)
    positive_feedback = build_positive_feedback(scores, main_feedback)
    summary = build_summary(main_feedback, positive_feedback)
    return PhraseSummary(
        phrase=phrase, scores=scores, summary=summary, main_feedback=main_feedback, positive_feedback=positive_feedback
    )
