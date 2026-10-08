"""Tests for chord->MIDI (Phase 13), progression->MIDI (14), accompaniment (15)."""

import shutil

import pretty_midi
import pytest

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_to_midi import chord_pitches, pitch_names
from hum.engine.accompanist.music.accompaniment import (
    render_accompaniment,
    BROKEN_PATTERN,
    MELODY_PROGRAM,
    _melody_min_pitch_in_range,
    _pitches_below_melody,
)
from hum.engine.accompanist.music.progression import generate_progression

_HAS_FLUIDSYNTH = shutil.which("fluidsynth") is not None


# ---------------------------------------------------------------------------
# Phase 13 — chord to MIDI pitches
# ---------------------------------------------------------------------------

def test_c_major_voicing():
    assert pitch_names(Chord("C", "major")) == ["C3", "E3", "G3"]
    assert chord_pitches(Chord("C", "major")) == [48, 52, 55]


def test_other_triads_ascending():
    # Each voicing should be strictly ascending.
    for chord in [Chord("F", "major"), Chord("G", "major"), Chord("A", "minor")]:
        p = chord_pitches(chord)
        assert p == sorted(p)
        assert len(p) == 3


# ---------------------------------------------------------------------------
# Phase 13/15 — broken-chord pattern
# ---------------------------------------------------------------------------

def test_broken_pattern_is_root_fifth_third_fifth():
    # C -> C G E G, F -> F C A C, G -> G D B D
    expected = {
        "C": ["C3", "G3", "E3", "G3"],
        "F": ["F3", "C4", "A3", "C4"],
        "G": ["G3", "D4", "B3", "D4"],
    }
    from music21 import pitch as m21pitch

    for root, want in expected.items():
        tri = chord_pitches(Chord(root, "major"))
        seq = [tri[i] for i in BROKEN_PATTERN]
        names = [m21pitch.Pitch(midi=m).nameWithOctave for m in seq]
        assert names == want


# ---------------------------------------------------------------------------
# Phase 13 — single chord to MIDI file
# ---------------------------------------------------------------------------

def test_single_chord_block_midi(tmp_path):
    out = tmp_path / "cmaj.mid"
    render_accompaniment([Chord("C", "major", 0, 4)], str(out), style="block",
                         tempo=120)
    pm = pretty_midi.PrettyMIDI(str(out))
    notes = pm.instruments[0].notes
    assert sorted(n.pitch for n in notes) == [48, 52, 55]
    # Block chord: all three start together.
    assert all(abs(n.start - notes[0].start) < 1e-6 for n in notes)


# ---------------------------------------------------------------------------
# Phase 14 — progression to MIDI
# ---------------------------------------------------------------------------

def test_progression_block_midi(tmp_path):
    prog = [
        Chord("C", "major", 0, 4),
        Chord("F", "major", 4, 4),
        Chord("G", "major", 8, 4),
        Chord("C", "major", 12, 4),
    ]
    out = tmp_path / "prog.mid"
    render_accompaniment(prog, str(out), style="block", tempo=120)
    pm = pretty_midi.PrettyMIDI(str(out))
    # 4 chords * 3 tones.
    assert len(pm.instruments[0].notes) == 12


# ---------------------------------------------------------------------------
# Phase 15 — melody + broken-chord accompaniment
# ---------------------------------------------------------------------------

def _eight_bar_melody():
    bar_notes = {
        0: [60, 64, 67, 72], 1: [65, 69, 72, 69], 2: [67, 71, 74, 67],
        3: [72, 67, 64, 60], 4: [69, 72, 76, 69], 5: [65, 69, 72, 65],
        6: [67, 71, 74, 71], 7: [60, 64, 67, 60],
    }
    melody = []
    for bar, ps in bar_notes.items():
        for beat, p in enumerate(ps):
            melody.append({"pitch": p, "start": bar * 4 + beat, "duration": 1.0})
    return melody


def test_accompaniment_has_melody_and_broken_chords(tmp_path):
    melody = _eight_bar_melody()
    prog = generate_progression(melody, "C", "major")
    out = tmp_path / "acc.mid"
    render_accompaniment(prog, str(out), style="broken", tempo=120,
                         melody_notes=melody)
    pm = pretty_midi.PrettyMIDI(str(out))
    assert len(pm.instruments) == 2
    # 8 bars * 4 broken notes.
    assert len(pm.instruments[0].notes) == 32
    # melody notes preserved.
    assert len(pm.instruments[1].notes) == 32


# ---------------------------------------------------------------------------
# Melody standout: distinct timbre + accompaniment stays below the melody
# ---------------------------------------------------------------------------


def test_melody_track_uses_a_distinct_instrument_from_the_accompaniment(tmp_path):
    melody = _eight_bar_melody()
    prog = generate_progression(melody, "C", "major")
    out = tmp_path / "acc.mid"
    render_accompaniment(prog, str(out), style="broken", tempo=120, melody_notes=melody)
    pm = pretty_midi.PrettyMIDI(str(out))
    accompaniment_track, melody_track = pm.instruments
    assert melody_track.program == MELODY_PROGRAM
    assert melody_track.program != accompaniment_track.program


def test_accompaniment_stays_below_the_melody_every_bar(tmp_path):
    """The whole point of register separation: no chord tone should ever sit
    at or above the melody note it's under, so the accompaniment can't mask
    the melody even when they'd otherwise land on the same pitch class."""
    melody = _eight_bar_melody()
    prog = generate_progression(melody, "C", "major")
    out = tmp_path / "acc.mid"
    render_accompaniment(prog, str(out), style="broken", tempo=120, melody_notes=melody)
    pm = pretty_midi.PrettyMIDI(str(out))
    accompaniment_track, melody_track = pm.instruments

    spb = 60.0 / 120.0
    for acc_note in accompaniment_track.notes:
        overlapping_melody = [
            m for m in melody_track.notes if m.start < acc_note.end and m.end > acc_note.start
        ]
        for m in overlapping_melody:
            assert acc_note.pitch < m.pitch, (
                f"accompaniment note {acc_note.pitch}@{acc_note.start / spb:.2f}beats "
                f"is not below overlapping melody note {m.pitch}"
            )


def test_no_melody_notes_leaves_accompaniment_unchanged(tmp_path):
    """Register separation must be strictly opt-in: calls that pass no
    melody (the vast majority of existing call sites) get byte-for-byte the
    same accompaniment as before this feature existed."""
    prog = [Chord("C", "major", 0, 4), Chord("F", "major", 4, 4)]
    with_no_melody = tmp_path / "no_melody.mid"
    render_accompaniment(prog, str(with_no_melody), style="block", tempo=120)
    pm = pretty_midi.PrettyMIDI(str(with_no_melody))
    assert len(pm.instruments) == 1
    assert sorted(n.pitch for n in pm.instruments[0].notes) == [48, 52, 53, 55, 57, 60]


class TestMelodyMinPitchHelper:
    def test_finds_lowest_overlapping_note(self):
        melody = [
            {"pitch": 67, "start": 0.0, "duration": 1.0},
            {"pitch": 60, "start": 1.0, "duration": 1.0},
        ]
        assert _melody_min_pitch_in_range(melody, 0.0, 2.0) == 60

    def test_ignores_notes_outside_the_range(self):
        melody = [{"pitch": 60, "start": 10.0, "duration": 1.0}]
        assert _melody_min_pitch_in_range(melody, 0.0, 4.0) is None

    def test_empty_melody_returns_none(self):
        assert _melody_min_pitch_in_range([], 0.0, 4.0) is None


class TestPitchesBelowMelodyHelper:
    def test_no_melody_pitch_is_a_no_op(self):
        assert _pitches_below_melody([48, 52, 55], None) == [48, 52, 55]

    def test_shifts_down_an_octave_when_clashing(self):
        # 67 (G4) clashes with a melody note at 67; must drop below it.
        result = _pitches_below_melody([60, 64, 67], melody_min_pitch=67)
        assert max(result) < 67
        assert result == [48, 52, 55]

    def test_default_floor_keeps_chords_out_of_the_mud(self):
        # Dropping [48, 52, 55] would land at C2-G2, below the A2 floor, so it stays put.
        assert _pitches_below_melody([48, 52, 55], melody_min_pitch=55) == [48, 52, 55]

    def test_already_below_melody_is_untouched(self):
        assert _pitches_below_melody([36, 40, 43], melody_min_pitch=55) == [36, 40, 43]

    def test_does_not_cross_the_floor(self):
        # A very low melody note should not push chords into subaudible range.
        result = _pitches_below_melody([24, 28, 31], melody_min_pitch=25, floor=24)
        assert result == [24, 28, 31]  # can't shift down without crossing the floor


@pytest.mark.skipif(not _HAS_FLUIDSYNTH, reason="fluidsynth not available")
def test_accompaniment_renders_to_wav(tmp_path):
    from hum.engine.accompanist.audio.render import render_midi, find_soundfont
    try:
        find_soundfont()
    except FileNotFoundError:
        pytest.skip("no soundfont available")

    melody = _eight_bar_melody()
    prog = generate_progression(melody, "C", "major")
    mid = tmp_path / "acc.mid"
    wav = tmp_path / "acc.wav"
    render_accompaniment(prog, str(mid), style="broken", tempo=120,
                         melody_notes=melody)
    render_midi(str(mid), str(wav))
    assert wav.is_file() and wav.stat().st_size > 0
