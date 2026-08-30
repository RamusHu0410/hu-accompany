"""Aligns a user's recorded notes to the expected notes for a phrase.

Pure objective matching -- no scores, no strings. A note flagged later as
having a "significant timing error" must still end up matched here (not
miscategorized as missing+extra), so the matching window is intentionally
wider than the timing-error thresholds in analysis.py.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import ExpectedNote, UserNote
from .pitch_utils import hz_to_cents

MIN_WINDOW_MS = 150.0
WINDOW_FRACTION_OF_BEAT = 0.5


@dataclass
class AlignmentResult:
    matched: List[Tuple[ExpectedNote, UserNote]]
    missing: List[ExpectedNote]
    extra: List[UserNote]


def _dedupe_by_note_id(user_notes: List[UserNote]) -> List[UserNote]:
    """If multiple detected notes share a note_id (e.g. partial/streaming
    detections), keep only the longest-duration one -- the most complete
    detection -- before matching."""
    best_by_id = {}
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
) -> AlignmentResult:
    expected_sorted = sorted(expected_notes, key=lambda n: n.start_time_ms)
    user_pool = _dedupe_by_note_id(sorted(user_notes, key=lambda n: n.start_time_ms))

    beat_ms = 60000.0 / bpm
    window_ms = max(WINDOW_FRACTION_OF_BEAT * beat_ms, MIN_WINDOW_MS)

    unmatched_user = list(user_pool)
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

    return AlignmentResult(matched=matched, missing=missing, extra=unmatched_user)
