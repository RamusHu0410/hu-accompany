"""Tests for melody -> MIDI conversion."""

import os

import pretty_midi

from hum.engine.accompanist.models.melody import Melody, Note
from hum.engine.accompanist.music.melody_to_midi import melody_to_midi


def make_melody() -> Melody:
    return Melody(
        notes=[
            Note(hz=60, start=0.0, duration=0.5),
            Note(hz=64, start=0.5, duration=0.5),
            Note(hz=67, start=1.0, duration=1.0),
        ],
        key="C",
        mode="major",
        tempo=100,
    )


def test_midi_file_is_created(tmp_path):
    # Step 2.2 — melody_to_midi(melody, "test.mid") then ls test.mid
    out = tmp_path / "test.mid"
    melody_to_midi(make_melody(), str(out))
    assert os.path.exists(out)


def test_midi_contents(tmp_path):
    # Step 2.3 — read the MIDI back and check note count and pitches
    out = tmp_path / "test.mid"
    melody_to_midi(make_melody(), str(out))

    pm = pretty_midi.PrettyMIDI(str(out))
    notes = pm.instruments[0].notes
    notes = sorted(notes, key=lambda n: n.start)

    assert len(notes) == 3
    assert notes[0].pitch == 60
    assert notes[1].pitch == 64
    assert notes[2].pitch == 67
