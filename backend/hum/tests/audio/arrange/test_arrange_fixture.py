"""The hand-written fixture melody is what the tests assume it is, and its MIDI twin agrees with it."""

import pretty_midi
import pytest

from hum.engine.audio.arrange.melody import key_pitch_classes, load_melody, melody_from_dict, parse_key

from conftest import FIXTURE_JSON, FIXTURE_MIDI


def consecutive(melody):
    return list(zip(melody.notes, melody.notes[1:]))


def test_header(melody):
    assert melody.tempo_bpm == 92.0
    assert melody.key == "D minor"
    assert melody.time_signature == "4/4"
    assert melody.tuning_offset_cents == 14
    assert melody.bars == 8


def test_is_monophonic_and_in_d_minor(melody):
    assert all(a.end_beats <= b.start_beats for a, b in consecutive(melody))
    assert {n.pitch % 12 for n in melody.notes} <= key_pitch_classes("D minor")


def test_has_a_dotted_rhythm(melody):
    assert any(a.duration_beats == 1.5 and b.duration_beats == 0.5 and a.end_beats == b.start_beats
               for a, b in consecutive(melody))


def test_has_a_repeated_note(melody):
    assert any(a.pitch == b.pitch for a, b in consecutive(melody))


def test_has_a_legato_step(melody):
    """Neighbouring scale notes with no gap between them."""
    assert any(abs(a.pitch - b.pitch) in (1, 2) and a.end_beats == b.start_beats for a, b in consecutive(melody))


def test_midi_twin_matches_the_json(melody):
    midi = pretty_midi.PrettyMIDI(str(FIXTURE_MIDI))
    assert len(midi.instruments) == 1
    assert midi.instruments[0].program == 0
    assert midi.get_tempo_changes()[1][0] == pytest.approx(92.0, abs=1e-3)
    spb = 60 / melody.tempo_bpm
    notes = sorted(midi.instruments[0].notes, key=lambda n: n.start)
    assert [n.pitch for n in notes] == [n.pitch for n in melody.notes]
    for mine, theirs in zip(notes, melody.notes):
        assert mine.start == pytest.approx(theirs.start_beats * spb, abs=2e-3)
        assert mine.end == pytest.approx(theirs.end_beats * spb, abs=2e-3)
        assert mine.velocity == theirs.velocity


@pytest.mark.parametrize("name, tonic, mode", [
    ("D minor", "D", "minor"), ("d minor", "D", "minor"), ("Bb major", "B-", "major"),
    ("B- major", "B-", "major"), ("F# minor", "F#", "minor"),
])
def test_key_names(name, tonic, mode):
    k = parse_key(name)
    assert (k.tonic.name, k.mode) == (tonic, mode)


@pytest.mark.parametrize("change, message", [
    ({"notes": []}, "no notes"),
    ({"tempo_bpm": 0}, "tempo"),
    ({"key": "H dorian"}, "key"),
    ({"time_signature": "4/5"}, "time signature"),
    ({"notes": [{"pitch": 200, "start_beats": 0, "duration_beats": 1}]}, "MIDI range"),
    ({"notes": [{"pitch": 60, "start_beats": 0, "duration_beats": 0}]}, "start/duration"),
])
def test_bad_melody_json_is_refused(change, message):
    data = load_melody(FIXTURE_JSON).to_dict() | change
    with pytest.raises(ValueError, match=message):
        melody_from_dict(data)


def test_six_decimal_triplets_become_exact():
    """Part A writes triplets as 0.333333; they're read as exact thirds of a beat."""
    data = load_melody(FIXTURE_JSON).to_dict() | {"notes": [
        {"pitch": 62, "start_beats": 0.0, "duration_beats": 0.333333},
        {"pitch": 64, "start_beats": 0.333333, "duration_beats": 0.333334},
        {"pitch": 65, "start_beats": 4.666667, "duration_beats": 0.333333},
    ]}
    notes = melody_from_dict(data).notes
    assert [n.start_beats for n in notes] == [0.0, 1 / 3, 14 / 3]
    assert notes[0].end_beats == notes[1].start_beats
    assert melody_from_dict(data | {"notes": [{"pitch": 60, "start_beats": 0.1234, "duration_beats": 1}]}).notes[0].start_beats == 0.1234
