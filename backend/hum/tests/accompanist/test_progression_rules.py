"""Tests for progression rules (Phase 12)."""

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.progression import generate_progression
from hum.engine.accompanist.music.progression_rules import (
    transition_score,
    degree_of,
    REPEAT_PENALTY,
)

C = Chord("C", "major")
F = Chord("F", "major")
G = Chord("G", "major")
Am = Chord("A", "minor")
Dm = Chord("D", "minor")


def _build_melody(bar_pitches: dict[int, list[int]]) -> list[dict]:
    melody = []
    for bar, pitches in bar_pitches.items():
        for beat, p in enumerate(pitches):
            melody.append({"pitch": p, "start": bar * 4 + beat, "duration": 1.0})
    return melody


# ---------------------------------------------------------------------------
# 12.1 repeat penalty
# ---------------------------------------------------------------------------

def test_repeat_is_penalized():
    assert transition_score(C, C, "C", "major") == REPEAT_PENALTY
    assert transition_score(C, F, "C", "major") > transition_score(C, C, "C", "major")


# ---------------------------------------------------------------------------
# 12.2 common transitions
# ---------------------------------------------------------------------------

def test_common_transitions_rewarded():
    for prev, cur in [(C, F), (C, G), (F, G), (G, C), (Am, F), (Dm, G)]:
        assert transition_score(prev, cur, "C", "major") > 0


def test_degree_mapping():
    assert degree_of(C, "C", "major") == 1
    assert degree_of(F, "C", "major") == 4
    assert degree_of(G, "C", "major") == 5
    assert degree_of(Am, "C", "major") == 6


# ---------------------------------------------------------------------------
# 12.3 cadence bonus
# ---------------------------------------------------------------------------

def test_cadence_bonus_only_at_end():
    mid = transition_score(G, C, "C", "major", is_final=False)
    final = transition_score(G, C, "C", "major", is_final=True)
    assert final > mid  # V -> I gets extra at the end


# ---------------------------------------------------------------------------
# 12.4 rules make an ambiguous melody more intentional
# ---------------------------------------------------------------------------

def _adjacent_repeats(prog):
    return sum(1 for i in range(1, len(prog)) if prog[i].symbol == prog[i - 1].symbol)


def _path_transition_score(prog, key="C", mode="major"):
    total = 0
    for i in range(1, len(prog)):
        total += transition_score(
            prog[i - 1], prog[i], key, mode, is_final=(i == len(prog) - 1)
        )
    return total


def test_rules_reduce_repeats_and_improve_flow():
    # Flat, ambiguous melody: greedy will just repeat the tonic.
    melody = _build_melody({b: [60, 60, 60, 60] for b in range(8)})

    greedy = generate_progression(melody, "C", "major", use_rules=False)
    ruled = generate_progression(melody, "C", "major", use_rules=True)

    # Greedy repeats the same chord; rules break that up substantially.
    assert _adjacent_repeats(greedy) > _adjacent_repeats(ruled)

    # Overall transition quality is substantially higher with rules.
    assert _path_transition_score(ruled) > _path_transition_score(greedy)

    # Resolves home to the tonic at the end.
    assert degree_of(ruled[-1], "C", "major") == 1


def test_rules_stay_in_key():
    melody = _build_melody({b: [60, 60, 60, 60] for b in range(8)})
    ruled = generate_progression(melody, "C", "major", use_rules=True)
    diatonic = {"C", "Dm", "Em", "F", "G", "Am", "Bdim"}
    assert all(c.symbol in diatonic for c in ruled)


def test_strong_melody_still_resolves_correctly():
    # The Phase 11 melody should still produce the intended progression.
    eight_bar = {
        0: [60, 64, 67, 72],
        1: [65, 69, 72, 69],
        2: [67, 71, 74, 67],
        3: [72, 67, 64, 60],
        4: [69, 72, 76, 69],
        5: [65, 69, 72, 65],
        6: [67, 71, 74, 71],
        7: [60, 64, 67, 60],
    }
    melody = _build_melody(eight_bar)
    prog = generate_progression(melody, "C", "major", use_rules=True)
    assert [c.symbol for c in prog] == ["C", "F", "G", "C", "Am", "F", "G", "C"]
