"""Top-level entry point: generate_feedback() wires alignment -> analysis ->
nlg together and returns a plain JSON-serializable dict, matching the
convention pdf_processor.process()/imslp_search.search_imslp() use of
returning plain dicts/lists at the package boundary rather than dataclasses.
"""

import dataclasses
from typing import List

from .alignment import align_notes
from .analysis import analyze_phrase
from .errors import InvalidNoteData
from .models import ExpectedNote, PhraseFeedbackResult, UserNote
from .nlg import build_immediate_feedback, build_phrase_summary


def _parse_expected_note(raw: dict) -> ExpectedNote:
    try:
        return ExpectedNote(
            note_id=raw["note_id"],
            pitch_hz=raw["pitch_hz"],
            start_time_ms=raw["start_time_ms"],
            end_time_ms=raw["end_time_ms"],
            duration_ms=raw["duration_ms"],
            vibrato_depth=raw.get("vibrato_depth"),
            pedal_action=raw.get("pedal_action"),
            has_accent=raw.get("has_accent"),
            markings=raw.get("markings"),
        )
    except KeyError as e:
        raise InvalidNoteData(f"expected note is missing required field: {e.args[0]}") from e
    except (TypeError, ValueError) as e:
        raise InvalidNoteData(f"expected note has an invalid value: {e}") from e


def _parse_user_note(raw: dict) -> UserNote:
    try:
        return UserNote(
            pitch_hz=raw["pitch_hz"],
            start_time_ms=raw["start_time_ms"],
            end_time_ms=raw["end_time_ms"],
            duration_ms=raw["duration_ms"],
            note_id=raw.get("note_id"),
            has_accent=raw.get("has_accent"),
        )
    except KeyError as e:
        raise InvalidNoteData(f"user note is missing required field: {e.args[0]}") from e
    except (TypeError, ValueError) as e:
        raise InvalidNoteData(f"user note has an invalid value: {e}") from e


def generate_feedback(phrase: int, bpm: float, expected_notes: List[dict], user_notes: List[dict]) -> dict:
    """Compare one recorded musical phrase against its expected-performance
    notes and return {"phrase", "immediate_feedback", "phrase_summary"} --
    see feedback_generator/README.md and api/views.py's phrase_feedback_view
    for the full field-by-field contract.
    """
    parsed_expected = [_parse_expected_note(note) for note in expected_notes]
    parsed_user = [_parse_user_note(note) for note in user_notes]

    alignment = align_notes(parsed_expected, parsed_user, bpm)
    analysis = analyze_phrase(alignment, bpm)

    immediate_feedback = build_immediate_feedback(analysis.errors)
    phrase_summary = build_phrase_summary(phrase, analysis.scores, analysis.errors, analysis.tempo_drift, bpm)

    result = PhraseFeedbackResult(phrase=phrase, immediate_feedback=immediate_feedback, phrase_summary=phrase_summary)
    return dataclasses.asdict(result)
