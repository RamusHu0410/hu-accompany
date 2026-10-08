"""Tests for chord scoring (Phase 8) and single-chord selection (Phase 9)."""

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_scoring import score_chord
from hum.engine.accompanist.music.chord_selection import choose_best_chord

CEG = [60, 64, 67]  # C E G


# ---------------------------------------------------------------------------
# Phase 8 — scoring
# ---------------------------------------------------------------------------

def test_chord_tones_score_highest():
    # C major contains all three notes of C-E-G -> max score (3 * 2).
    assert score_chord(Chord("C", "major"), CEG) == 6


def test_relative_ranking_for_ceg():
    scores = {
        "C": score_chord(Chord("C", "major"), CEG),
        "Am": score_chord(Chord("A", "minor"), CEG),
        "Em": score_chord(Chord("E", "minor"), CEG),
        "F": score_chord(Chord("F", "major"), CEG),
        "G": score_chord(Chord("G", "major"), CEG),
        "Dm": score_chord(Chord("D", "minor"), CEG),
        "Bdim": score_chord(Chord("B", "diminished"), CEG),
    }
    # C is strictly the best fit.
    assert scores["C"] == max(scores.values())
    # High-fit chords (share 2 chord tones) beat medium, which beat low.
    assert scores["Am"] > scores["F"]
    assert scores["Em"] > scores["Dm"]
    assert scores["F"] >= scores["Bdim"]


def test_out_of_scale_note_penalized():
    # C# (61) is not in C major -> clash penalty, lowering the score.
    with_clash = score_chord(Chord("C", "major"), [60, 61, 64])
    without_clash = score_chord(Chord("C", "major"), [60, 64])
    assert with_clash < without_clash


# ---------------------------------------------------------------------------
# Phase 9 — best single chord
# ---------------------------------------------------------------------------

def test_choose_best_chord_ceg():
    assert choose_best_chord([60, 64, 67]).symbol == "C"


def test_choose_best_chord_fac():
    assert choose_best_chord([65, 69, 72]).symbol == "F"


def test_choose_best_chord_gbd():
    assert choose_best_chord([67, 71, 74]).symbol == "G"
