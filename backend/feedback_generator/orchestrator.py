"""Wiring only: parse the request, align the notes, run the judges, hand the
pieces to summarizer.py, return plain JSON-serializable dicts.

No feedback text and no rating logic live here -- every message and every
0-100 comes from a module in judges/, and every aggregate from
summarizer.py. Returning plain dicts at the package boundary matches
pdf_processor.process() and imslp_search.search_imslp().

Two phases:

  judge_phrase()  phase 1 -- one submitted phrase against its expected
                  notes. Bar-by-bar findings and per-dimension ratings, no
                  summary. Stored as Phase1/Phrase<n>.json.
  judge_piece()   phase 2 -- every stored phase-1 phrase at once. The
                  whole-piece summary plus the phase-2 judges (era). Stored
                  as Phase2/Summary.json and Phase2/<Judge>.json.
"""

import dataclasses
from typing import Dict, List, Optional, Tuple

from .errors import InvalidNoteData
from .judges import (
    ExpectedNote,
    PhraseContext,
    UserNote,
    bar_of,
    bar_span,
    beats_per_bar,
    hz_to_cents,
    overall_score,
    phase1_judges,
    phase2_judges,
)
from .summarizer import build_piece_context, summarize

# A note flagged later as badly late must still be *matched* here (not
# reported as one missing plus one extra note), so the matching window is
# deliberately wider than rhythm.py's timing thresholds.
MIN_WINDOW_MS = 150.0
WINDOW_FRACTION_OF_BEAT = 0.5


# --- Request parsing ----------------------------------------------------------

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


# --- Alignment ----------------------------------------------------------------

def _dedupe_by_note_id(user_notes: List[UserNote]) -> List[UserNote]:
    """If several detected notes share a note_id (partial/streaming
    detections), keep only the longest -- the most complete detection."""
    best_by_id: Dict[int, UserNote] = {}
    unlabeled = []
    for note in user_notes:
        if note.note_id is None:
            unlabeled.append(note)
            continue
        current = best_by_id.get(note.note_id)
        if current is None or note.duration_ms > current.duration_ms:
            best_by_id[note.note_id] = note
    return list(best_by_id.values()) + unlabeled


def _match_score(expected: ExpectedNote, user: UserNote, window_ms: float) -> float:
    time_diff = abs(user.start_time_ms - expected.start_time_ms)
    cents_diff = abs(hz_to_cents(user.pitch_hz, expected.pitch_hz))
    return time_diff / window_ms + 0.5 * min(cents_diff / 1200.0, 1.0)


def align_notes(
    expected_notes: List[ExpectedNote], user_notes: List[UserNote], bpm: float
) -> Tuple[List[Tuple[ExpectedNote, UserNote]], List[ExpectedNote], List[UserNote]]:
    """(matched, missing, extra) -- purely objective pairing, no judgement."""
    expected_sorted = sorted(expected_notes, key=lambda n: n.start_time_ms)
    unmatched_user = _dedupe_by_note_id(sorted(user_notes, key=lambda n: n.start_time_ms))

    window_ms = max(WINDOW_FRACTION_OF_BEAT * (60000.0 / bpm), MIN_WINDOW_MS)

    matched: List[Tuple[ExpectedNote, UserNote]] = []
    missing: List[ExpectedNote] = []

    for expected in expected_sorted:
        # Validated id-hint shortcut: only trust note_id if it's also within
        # the timing window, so a stale/copied id can't pair notes that
        # aren't actually the same performance event.
        id_hint = next(
            (
                u
                for u in unmatched_user
                if u.note_id == expected.note_id
                and abs(u.start_time_ms - expected.start_time_ms) <= window_ms
            ),
            None,
        )
        if id_hint is not None:
            matched.append((expected, id_hint))
            unmatched_user.remove(id_hint)
            continue

        candidates = [
            u for u in unmatched_user if abs(u.start_time_ms - expected.start_time_ms) <= window_ms
        ]
        if not candidates:
            missing.append(expected)
            continue

        best = min(candidates, key=lambda u: _match_score(expected, u, window_ms))
        matched.append((expected, best))
        unmatched_user.remove(best)

    return matched, missing, unmatched_user


# --- Phase 1: one phrase ------------------------------------------------------

def judge_phrase(
    phrase: int,
    bpm: float,
    expected_notes: List[dict],
    user_notes: List[dict],
    time_signature: Optional[str] = None,
) -> dict:
    """Compare one recorded phrase against its expected notes.

    Returns the phase-1 file body:
        {"phrase", "bpm", "time_signature", "bars": [first, last],
         "scores": {overall, pitch, rhythm, tempo, dynamics, articulation},
         "feedback": [{bars, category, severity, confidence, message,
                       details}, ...]}
    `feedback` is ordered by bar, then by the order judges run in.
    """
    parsed_expected = [_parse_expected_note(note) for note in expected_notes]
    parsed_user = [_parse_user_note(note) for note in user_notes]

    per_bar = beats_per_bar(time_signature)
    matched, missing, extra = align_notes(parsed_expected, parsed_user, bpm)
    ctx = PhraseContext(
        phrase=phrase, bpm=bpm, beats_per_bar=per_bar, matched=matched, missing=missing, extra=extra
    )

    findings = []
    scores: Dict[str, Optional[int]] = {}
    for index, judge_module in enumerate(phase1_judges()):
        result = judge_module.judge(ctx)
        scores[result.category] = result.score
        findings.extend((finding.bars, index, finding) for finding in result.findings)

    findings.sort(key=lambda entry: (entry[0], entry[1]))
    bars = bar_span(bar_of(note.start_time_ms, bpm, per_bar) for note in parsed_expected)

    return {
        "phrase": phrase,
        "bpm": bpm,
        "time_signature": time_signature or None,
        "bars": bars,
        "scores": {"overall": overall_score(scores), **scores},
        "feedback": [dataclasses.asdict(finding) for _, _, finding in findings],
    }


# --- Phase 2: the whole piece -------------------------------------------------

def judge_piece(phrases: List[dict], piece: Optional[dict] = None) -> Dict[str, dict]:
    """Run phase 2 over every stored phase-1 phrase file.

    Returns one entry per Phase2 file, keyed by file stem:
        {"Summary": {...}, "Era": {...}}
    Each phase-2 judge contributes its own file, so a judge that had nothing
    to say (era with no composition date) still stores its empty envelope
    rather than silently disappearing.
    """
    ctx = build_piece_context(piece, phrases)
    files = {"Summary": summarize(ctx)}

    for judge_module in phase2_judges():
        result = judge_module.judge(ctx)
        files[judge_module.NAME.capitalize()] = {
            "type": result.category,
            "score": result.score,
            **result.details,
            "feedback": [dataclasses.asdict(finding) for finding in result.findings],
        }

    return files
