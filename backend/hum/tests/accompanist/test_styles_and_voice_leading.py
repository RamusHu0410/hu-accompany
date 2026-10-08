"""Tests for accompaniment styles (Phase 16) and voice leading (Phase 17)."""

import pretty_midi

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.accompaniment import render_accompaniment
from hum.engine.accompanist.music.styles import STYLES
from hum.engine.accompanist.music.voice_leading import (
    naive_voicings,
    lead_voices,
    total_movement,
    voicing_distance,
)

PROG = [Chord("C", "major"), Chord("F", "major"), Chord("G", "major")]


# ---------------------------------------------------------------------------
# Phase 16 — styles
# ---------------------------------------------------------------------------

def test_all_styles_registered():
    # The four core styles must always be present (scale-flavored styles like
    # jazz/asian_folk may be added alongside them).
    assert {"piano", "pop", "cinematic", "classical"} <= set(STYLES)


def test_styles_produce_notes(tmp_path):
    prog = [Chord("C", "major", 0, 4), Chord("F", "major", 4, 4)]
    for style in STYLES:
        out = tmp_path / f"{style}.mid"
        render_accompaniment(prog, str(out), style=style, tempo=120)
        pm = pretty_midi.PrettyMIDI(str(out))
        assert len(pm.instruments[0].notes) > 0


def test_pop_is_busier_than_piano(tmp_path):
    prog = [Chord("C", "major", 0, 4), Chord("F", "major", 4, 4)]
    counts = {}
    for style in ("piano", "pop"):
        out = tmp_path / f"{style}.mid"
        render_accompaniment(prog, str(out), style=style, tempo=120)
        counts[style] = len(pretty_midi.PrettyMIDI(str(out)).instruments[0].notes)
    # Pop has an extra chord subdivision per bar.
    assert counts["pop"] > counts["piano"]


def test_cinematic_has_sustained_bass(tmp_path):
    prog = [Chord("C", "major", 0, 4)]
    out = tmp_path / "cin.mid"
    render_accompaniment(prog, str(out), style="cinematic", tempo=120)
    pm = pretty_midi.PrettyMIDI(str(out))
    notes = pm.instruments[0].notes
    # The lowest note should span (roughly) the whole bar (4 beats @120 = 2s).
    lowest = min(notes, key=lambda n: n.pitch)
    assert (lowest.end - lowest.start) >= 1.9


# ---------------------------------------------------------------------------
# Phase 17 — voice leading
# ---------------------------------------------------------------------------

def test_voice_leading_reduces_movement():
    naive = naive_voicings(PROG, octave=4)
    led = lead_voices(PROG, octave=4)

    before = total_movement(naive)
    after = total_movement(led)

    # Movement should decrease (spec: ~20 -> ~12).
    assert after < before
    assert before >= 18
    assert after <= 14


def test_voice_leading_preserves_pitch_classes():
    # Re-voicing must keep the same chord (same pitch classes) each step.
    led = lead_voices(PROG, octave=4)
    for chord, voicing in zip(PROG, led):
        from hum.engine.accompanist.music.chord_to_midi import chord_pitches

        expected_pcs = {p % 12 for p in chord_pitches(chord, 4)}
        got_pcs = {p % 12 for p in voicing}
        assert got_pcs == expected_pcs


def test_voicing_distance_symmetric():
    a = [60, 64, 67]
    b = [59, 62, 67]
    assert voicing_distance(a, b) == voicing_distance(b, a)


def test_matches_spec_example():
    # Naive C-F-G in root position vs the voice-led target from the spec.
    led = lead_voices(PROG, octave=4)
    # First chord stays C4 E4 G4.
    assert led[0] == [60, 64, 67]
    # Subsequent chords stay close to the previous voicing.
    assert voicing_distance(led[0], led[1]) <= 6
    assert voicing_distance(led[1], led[2]) <= 6
