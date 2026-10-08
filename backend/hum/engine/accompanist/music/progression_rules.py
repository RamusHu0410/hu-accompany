"""Transition rules that shape a progression to sound intentional.

Scores are expressed over scale degrees (roman numerals) so the rules apply
in any key. Degrees are 1-7 (I..vii).
"""

from __future__ import annotations

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_candidates import get_candidates

# --- weights -------------------------------------------------------------
REPEAT_PENALTY = -3        # same chord twice in a row (12.1)
COMMON_TRANSITION_BONUS = 2  # a strong functional move (12.2)
CADENCE_BONUS = 5          # V -> I at the very end (12.3)

# Common/strong functional transitions, as (from_degree, to_degree).
_COMMON_TRANSITIONS = {
    (1, 4),  # I  -> IV
    (1, 5),  # I  -> V
    (4, 5),  # IV -> V
    (5, 1),  # V  -> I
    (6, 4),  # vi -> IV
    (2, 5),  # ii -> V
    (4, 1),  # IV -> I  (plagal)
    (2, 4),  # ii -> IV
    (6, 2),  # vi -> ii
}


def degree_of(chord: Chord, key: str, mode: str) -> int | None:
    """Return the 1-based scale degree of a chord within a key, or None.

    Matches by root pitch class against the diatonic candidates.
    """
    from music21 import pitch as m21pitch

    target = m21pitch.Pitch(chord.root).midi % 12
    for i, cand in enumerate(get_candidates(key, mode)):
        if m21pitch.Pitch(cand.root).midi % 12 == target:
            return i + 1
    return None


def transition_score(
    prev: Chord,
    cur: Chord,
    key: str,
    mode: str,
    is_final: bool = False,
) -> int:
    """Score the move from prev -> cur.

    Combines: repeat penalty, common-transition bonus, and (on the final move)
    a cadence bonus for V -> I.
    """
    score = 0
    d_prev = degree_of(prev, key, mode)
    d_cur = degree_of(cur, key, mode)

    # 12.1 penalize repeats
    if prev.symbol == cur.symbol:
        score += REPEAT_PENALTY

    if d_prev is not None and d_cur is not None:
        # 12.2 reward common transitions
        if (d_prev, d_cur) in _COMMON_TRANSITIONS:
            score += COMMON_TRANSITION_BONUS

        # 12.3 reward an authentic cadence at the end
        if is_final and d_prev == 5 and d_cur == 1:
            score += CADENCE_BONUS

    return score
