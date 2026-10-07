"""Tests for segmentation (Phase 10) and progression generation (Phase 11)."""

from hum.engine.accompanist.music.segmentation import segment_by_bar
from hum.engine.accompanist.music.progression import generate_progression


def _build_melody(bar_pitches: dict[int, list[int]]) -> list[dict]:
    """Turn {bar: [pitch,...]} into quarter-note melody dicts."""
    melody = []
    for bar, pitches in bar_pitches.items():
        for beat, p in enumerate(pitches):
            melody.append({"pitch": p, "start": bar * 4 + beat, "duration": 1.0})
    return melody


# Chord-tone content per bar spelling C F G C Am F G C.
EIGHT_BAR = {
    0: [60, 64, 67, 72],  # C
    1: [65, 69, 72, 69],  # F
    2: [67, 71, 74, 67],  # G
    3: [72, 67, 64, 60],  # C
    4: [69, 72, 76, 69],  # Am
    5: [65, 69, 72, 65],  # F
    6: [67, 71, 74, 71],  # G
    7: [60, 64, 67, 60],  # C
}


# ---------------------------------------------------------------------------
# Phase 10 — segmentation
# ---------------------------------------------------------------------------

def test_eight_bars_gives_eight_segments():
    melody = _build_melody(EIGHT_BAR)
    segments = segment_by_bar(melody)
    assert len(segments) == 8
    assert all(len(s) == 4 for s in segments)


def test_notes_land_in_correct_bar():
    melody = _build_melody(EIGHT_BAR)
    segments = segment_by_bar(melody)
    # First note of bar 2 (index 1) starts at beat 4.
    assert segments[1][0]["start"] == 4


# ---------------------------------------------------------------------------
# Phase 11 — progression
# ---------------------------------------------------------------------------

def test_progression_matches_expected():
    melody = _build_melody(EIGHT_BAR)
    prog = generate_progression(melody, key="C", mode="major")
    symbols = [c.symbol for c in prog]
    assert symbols == ["C", "F", "G", "C", "Am", "F", "G", "C"]


def test_progression_timing_spans_bars():
    melody = _build_melody(EIGHT_BAR)
    prog = generate_progression(melody, key="C", mode="major")
    assert [c.start for c in prog] == [0, 4, 8, 12, 16, 20, 24, 28]
    assert all(c.duration == 4 for c in prog)


def test_progression_stays_in_key():
    # Every chord must be one of the diatonic C-major triads.
    melody = _build_melody(EIGHT_BAR)
    prog = generate_progression(melody, key="C", mode="major")
    diatonic = {"C", "Dm", "Em", "F", "G", "Am", "Bdim"}
    assert all(c.symbol in diatonic for c in prog)
