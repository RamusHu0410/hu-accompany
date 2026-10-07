"""Tests for the melody models."""

import json

from hum.engine.accompanist.models.melody import Melody, Note

TEST_JSON = """
{
  "melody": [
    {"hz": 60, "start": 0, "duration": 0.5},
    {"hz": 64, "start": 0.5, "duration": 0.5},
    {"hz": 67, "start": 1, "duration": 1}
  ],
  "key": "C",
  "mode": "major",
  "tempo": 100
}
"""


def test_melody_from_kingsley_json():
    data = json.loads(TEST_JSON)
    melody = Melody.from_dict(data)

    # Structure
    assert len(melody.notes) == 3
    assert all(isinstance(n, Note) for n in melody.notes)

    # Musical context
    assert melody.key == "C"
    assert melody.mode == "major"
    assert melody.tempo == 100

    # Notes parsed correctly
    assert melody.notes[0] == Note(hz=60, start=0, duration=0.5)
    assert melody.notes[1] == Note(hz=64, start=0.5, duration=0.5)
    assert melody.notes[2] == Note(hz=67, start=1, duration=1)


import math

import pytest


@pytest.mark.parametrize(
    ("notes", "said"),
    [
        ([{"hz": 60, "start": 0}], "must have hz, start and duration"),
        (["C4"], "must have hz, start and duration"),
        ([{"hz": "60", "start": 0, "duration": 1}], "finite number"),
        ([{"hz": math.nan, "start": 0, "duration": 1}], "finite number"),
        ([{"hz": True, "start": 0, "duration": 1}], "finite number"),
        ([{"hz": 128, "start": 0, "duration": 1}], "MIDI note number"),
        ([{"hz": 60, "start": -1, "duration": 1}], "can't be negative"),
        ([{"hz": 60, "start": 0, "duration": 0}], "must be positive"),
    ],
)
def test_from_dict_rejects_unusable_notes_with_a_clear_reason(notes, said):
    with pytest.raises(ValueError, match=said):
        Melody.from_dict({"melody": notes})


@pytest.mark.parametrize("tempo", [0, -60, 1000, "fast"])
def test_from_dict_rejects_an_unusable_tempo(tempo):
    with pytest.raises(ValueError, match="tempo"):
        Melody.from_dict({"melody": [], "tempo": tempo})


def test_from_dict_rejects_a_melody_that_is_not_a_list():
    with pytest.raises(ValueError, match="list"):
        Melody.from_dict({"melody": "C D E"})
