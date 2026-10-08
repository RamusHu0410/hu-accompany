"""How people really hum: legato steps with no gap, repeated notes, vibrato on a long note.

These check the notes: their pitches, and when each starts (in seconds from the first, within a
tenth of a second). A tune of three or four notes fits more than one tempo, so the exact beats are
left to test_hum_sample and test_units.
"""

import json

import pytest

from hum.engine.audio.intake import transcribe_to_melody

from .hum_synth import Sung, hum, write

TEMPO = 120
SECONDS_PER_BEAT = 60 / TEMPO


def _melody(tmp_path, notes, **options):
    """The notes heard, as (pitch, start in seconds from the first note)."""
    source = write(tmp_path / "hum.wav", hum(notes, tempo=TEMPO, **options))
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    with open(result.json_path) as file:
        melody = json.load(file)
    return result, [(n["pitch"], n["start_beats"] * 60 / melody["tempo_bpm"]) for n in melody["notes"]]


def _sung(*pitches_and_beats):
    return [(pitch, pytest.approx(beat * SECONDS_PER_BEAT, abs=0.1)) for pitch, beat in pitches_and_beats]


def test_legato_steps_with_no_gap_are_separate_notes(tmp_path):
    # C3 D3 E3 F3, sung straight on, no pause between them
    steps = [Sung(48, 0, 1, scoop=True), Sung(50, 1, 1, "legato"), Sung(52, 2, 1, "legato"), Sung(53, 3, 1, "legato")]
    result, notes = _melody(tmp_path, steps)
    assert notes == _sung((48, 0), (50, 1), (52, 2), (53, 3))
    assert not result.fell_back


def test_repeated_notes_with_a_brief_dip_stay_separate(tmp_path):
    repeats = [Sung(50, 0, 1), Sung(50, 1, 1, "dip"), Sung(50, 2, 1, "dip"), Sung(53, 3, 1)]
    _, notes = _melody(tmp_path, repeats)
    assert notes == _sung((50, 0), (50, 1), (50, 2), (53, 3))


def test_vibrato_and_drift_on_a_held_note_stay_one_note(tmp_path):
    held = [Sung(50, 0, 1), Sung(53, 1, 4, "legato", vibrato=True), Sung(52, 5, 1)]
    _, notes = _melody(tmp_path, held, vibrato_semitones=0.5)  # a wide vibrato: half a semitone each way
    assert notes == _sung((50, 0), (53, 1), (52, 5))


def test_scoops_into_notes_do_not_add_notes(tmp_path):
    scooped = [Sung(50, 0, 1, scoop=True), Sung(52, 1, 1, scoop=True), Sung(53, 2, 2, scoop=True)]
    _, notes = _melody(tmp_path, scooped)
    assert notes == _sung((50, 0), (52, 1), (53, 2))
