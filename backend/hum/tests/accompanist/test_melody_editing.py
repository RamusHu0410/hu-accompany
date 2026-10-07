"""Tests for allow_edit_melody and jazz melody styling."""

import random

from hum.engine.accompanist.generate import generate_accompaniment
from hum.engine.accompanist.music.scales import scale_pitch_classes
from hum.engine.accompanist.music.melody_styling import jazz_stylize


def _melody():
    # Includes a chromatic note (61 = C#) and off-beat notes.
    return {
        "melody": [
            {"hz": 60, "start": 0, "duration": 0.5},
            {"hz": 61, "start": 0.5, "duration": 0.5},   # C# — out of jazz scale
            {"hz": 64, "start": 1, "duration": 0.5},
            {"hz": 67, "start": 1.5, "duration": 0.5},   # off-beat
        ],
        "tempo": 120,
    }


def test_melody_unedited_by_default(tmp_path):
    result = generate_accompaniment(
        _melody(), str(tmp_path / "a.mid"), style="jazz", key="C", mode="major",
        allow_edit_melody=False,
    )
    pitches = [n["pitch"] for n in result.melody_notes]
    # C# (61) survives untouched when editing is off.
    assert 61 in pitches
    assert any("left unedited" in w for w in result.warnings)


def test_melody_edited_when_allowed(tmp_path):
    result = generate_accompaniment(
        _melody(), str(tmp_path / "b.mid"), style="jazz", key="C", mode="major",
        allow_edit_melody=True,
    )
    pitches = [n["pitch"] for n in result.melody_notes]
    allowed = scale_pitch_classes("C", "jazz")
    # Every edited melody note is now in the jazz scale (C# snapped away).
    assert all(p % 12 in allowed for p in pitches)
    assert any("jazz feel" in w for w in result.warnings)


def test_non_scale_style_ignores_flag(tmp_path):
    # A plain style never edits the melody regardless of the flag.
    result = generate_accompaniment(
        _melody(), str(tmp_path / "c.mid"), style="piano", key="C", mode="major",
        allow_edit_melody=True,
    )
    pitches = [n["pitch"] for n in result.melody_notes]
    assert 61 in pitches  # chromatic note preserved
    assert not any("edited" in w.lower() for w in result.warnings)


def test_jazz_stylize_snaps_and_swings():
    random.seed(0)
    notes = [
        {"pitch": 61, "start": 0.0, "duration": 0.5},   # on-beat, chromatic
        {"pitch": 67, "start": 0.5, "duration": 0.5},   # off-beat
    ]
    out = jazz_stylize(notes, "C", "jazz")
    allowed = scale_pitch_classes("C", "jazz")
    # All output pitches are in the jazz scale.
    assert all(n["pitch"] % 12 in allowed for n in out)
    # The off-beat note (start 0.5) is delayed (swing push) -> start > 0.5.
    offbeat = [n for n in out if abs(n["start"] - 0.5) < 0.3 and n["pitch"] % 12 in allowed]
    assert any(n["start"] > 0.5 for n in offbeat)
