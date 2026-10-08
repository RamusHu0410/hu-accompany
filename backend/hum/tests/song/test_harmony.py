"""Chords for a tune (hum/song/harmony.py) and how they're voiced (hum/song/parts.py)."""

import pytest

from hum.song.harmony import Chord, chord_by_degree, colored, key_chords, progression
from hum.song.parts import bass_bar, chord_bar, pad_bar, voice
from hum.song.presets import MOODS, PRESETS
from hum.song.project import Note
from hum.transcription import SCALES

POP, JAZZ, ROCK = PRESETS["pop"], PRESETS["jazz"], PRESETS["rock"]
NEUTRAL = MOODS["neutral"]


def bars_of(*arpeggios) -> list[Note]:
    """A tune that spells one chord per bar, a beat a note."""
    return [Note(p, bar * 4 + i, 1, 90) for bar, pitches in enumerate(arpeggios) for i, p in enumerate(pitches)]


def degrees(chords) -> list[str]:
    return [c.degree for c in chords]


def test_a_tune_that_spells_its_chords_gets_those_chords_in_major():
    tune = bars_of((60, 64, 67, 64), (65, 69, 72, 69), (67, 71, 74, 71), (72, 67, 64, 60))
    assert degrees(progression(tune, 4, 0, "major", POP, NEUTRAL)) == ["I", "IV", "V", "I"]


def test_and_in_minor_with_the_raised_seventh():
    tune = bars_of((57, 60, 64, 60), (62, 65, 69, 65), (64, 68, 71, 68), (69, 64, 60, 57))
    chords = progression(tune, 4, 9, "minor", POP, NEUTRAL)
    assert degrees(chords) == ["i", "iv", "V", "i"]
    assert chords[2].pitch_classes == (4, 8, 11)  # E major: the G sharp is the tune's


@pytest.mark.parametrize("mode", ["major", "minor"])
@pytest.mark.parametrize("tonic", [0, 2, 7, 10])
def test_every_chord_belongs_to_the_key(tonic, mode):
    scale = {(tonic + step) % 12 for step in SCALES[mode]}
    for chord in key_chords(tonic, mode):
        assert set(chord.pitch_classes) <= scale
        assert set(colored(chord, JAZZ).pitch_classes) <= scale


def test_an_ambiguous_tune_starts_and_ends_at_home():
    tune = [Note(67, 0, 16, 90)]  # one long G over four bars: C, Em and G major all fit
    chords = progression(tune, 4, 0, "major", POP, NEUTRAL)
    assert chords[0].degree == "I" and chords[-1].degree == "I"


def test_the_mood_settles_a_close_call():
    tune = [Note(64, 0, 4, 90), Note(64, 4, 4, 90)]  # E fits C major and E minor (and A minor)
    dark = progression(tune, 2, 0, "major", POP, MOODS["dark"])
    bright = progression(tune, 2, 0, "major", POP, MOODS["bright"])
    assert dark[1].quality == "min"
    assert bright[1].quality == "maj"


def test_the_progression_never_fights_a_held_note():
    tune = [Note(62, 0, 4, 90), Note(62, 4, 4, 90), Note(62, 8, 4, 90)]  # D, in C major
    for chord in progression(tune, 3, 0, "major", POP, NEUTRAL)[1:]:
        assert 2 in chord.pitch_classes


def test_genres_color_their_chords():
    five = chord_by_degree(0, "major", "V")
    two = chord_by_degree(0, "major", "ii")
    assert colored(five, JAZZ).quality == "dom7" and colored(two, JAZZ).quality == "min7"
    assert colored(five, ROCK).quality == "power"
    assert colored(five, POP) == five
    assert Chord(9, "min7", "vi").name() == "Am7" and Chord(10, "maj", "IV").name() == "Bb"


# ── Voicing ────────────────────────────────────────────────────────────


def test_voicings_stay_under_the_ceiling_and_move_smoothly():
    chords = [chord_by_degree(0, "major", d) for d in ("I", "vi", "IV", "V", "I")]
    previous = None
    for chord in chords:
        notes = voice(chord, 48, 59, previous)
        assert all(48 <= n <= 59 for n in notes)
        assert {n % 12 for n in notes} == set(chord.pitch_classes)
        if previous:
            assert max(abs(a - b) for a, b in zip(sorted(previous), sorted(notes))) <= 4  # no voice leaps past a third
        previous = notes


def test_a_cramped_range_keeps_the_chord_under_the_tune():
    notes = voice(chord_by_degree(0, "major", "I"), 55, 58, None)
    assert max(notes) <= 58


def test_patterns_land_inside_their_bar():
    voicing = voice(chord_by_degree(0, "major", "I"), 48, 59, None)
    for pattern in ("hold", "pulse", "lofi", "power8", "stab", "charleston", "strum", "arp"):
        for note in chord_bar(voicing, pattern, 3, 80):
            assert 12 <= note.start < 16 and note.end <= 16 + 1e-9


@pytest.mark.parametrize("line", ["hold", "root_fifth", "eighths", "lofi", "offbeat", "walking"])
def test_the_bass_starts_from_the_root_and_stays_low(line):
    c, f = chord_by_degree(0, "major", "I"), chord_by_degree(0, "major", "IV")
    notes = bass_bar(c, f, line, 0, 90)
    assert all(n.pitch < 48 for n in notes)
    assert notes[0].pitch % 12 == 0
    if line == "walking":
        assert notes[-1].pitch == 28  # steps into F from E, the note below it in C major
        assert bass_bar(c, f, line, 0, 90, scale=frozenset((0, 2, 4, 5, 7, 9, 11)))[-1].pitch == 28


def test_the_pad_never_reaches_the_tune():
    for ceiling in (52, 59, 64, 71):
        assert all(n.pitch <= ceiling for n in pad_bar(chord_by_degree(0, "major", "V"), ceiling, 0, 60))
