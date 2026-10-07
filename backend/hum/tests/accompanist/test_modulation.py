"""Tests for key/mode modulation (transposing the piece)."""

from hum.engine.accompanist.generate import generate_accompaniment
from hum.engine.accompanist.music.modulation import (
    transpose_interval,
    modulate_notes,
    resolve_target,
)


def _melody():
    bar_notes = {0: [60, 64, 67, 72], 1: [65, 69, 72, 69],
                 2: [67, 71, 74, 67], 3: [72, 67, 64, 60]}
    notes = []
    for bar, ps in bar_notes.items():
        for beat, p in enumerate(ps):
            notes.append({"hz": p, "start": bar * 4 + beat, "duration": 1.0})
    return {"melody": notes, "key": "C", "mode": "major", "tempo": 120}


# ---------------------------------------------------------------------------
# unit: interval / note transposition
# ---------------------------------------------------------------------------

def test_transpose_interval_nearest():
    # C -> G is -5 (down a fourth) rather than +7 (up a fifth).
    assert transpose_interval("C", "G") == -5
    assert transpose_interval("C", "D") == 2
    assert transpose_interval("C", "C") == 0


def test_modulate_notes_shifts_pitch_only():
    notes = [{"pitch": 60, "start": 0, "duration": 1}]
    out = modulate_notes(notes, "C", "D")
    assert out[0]["pitch"] == 62
    assert out[0]["start"] == 0
    assert out[0]["duration"] == 1


def test_resolve_target_mode_switch():
    key, mode, shift = resolve_target("C", "major", None, "minor")
    assert key == "C" and mode == "minor" and shift == 0


def test_resolve_target_rejects_bad_mode():
    import pytest
    with pytest.raises(ValueError):
        resolve_target("C", "major", "C", "lydian")


# ---------------------------------------------------------------------------
# end-to-end through generate_accompaniment
# ---------------------------------------------------------------------------

def test_modulate_to_g_major(tmp_path):
    r = generate_accompaniment(_melody(), str(tmp_path / "g.mid"),
                               style="piano", key="C", mode="major",
                               modulate_to_key="G")
    assert r.key == "G" and r.mode == "major"
    assert r.progression_symbols == ["G", "C", "D", "G"]
    # first melody note C4 (60) -> G3 (55)
    assert r.melody_notes[0]["pitch"] == 55


def test_switch_to_minor(tmp_path):
    r = generate_accompaniment(_melody(), str(tmp_path / "m.mid"),
                               style="piano", key="C", mode="major",
                               modulate_to_mode="minor")
    assert r.key == "C" and r.mode == "minor"
    # Diatonic chords are now minor-mode.
    assert all(s.endswith("m") or s.endswith("dim") for s in r.progression_symbols)


def test_modulate_to_a_minor(tmp_path):
    r = generate_accompaniment(_melody(), str(tmp_path / "a.mid"),
                               style="piano", key="C", mode="major",
                               modulate_to_key="A", modulate_to_mode="minor")
    assert r.key == "A" and r.mode == "minor"
    assert r.melody_notes[0]["pitch"] == 57  # C4 -> A3
    diatonic_amin = {"Am", "Bdim", "C", "Dm", "Em", "F", "G"}
    assert all(s in diatonic_amin for s in r.progression_symbols)


def test_no_modulation_leaves_key_unchanged(tmp_path):
    r = generate_accompaniment(_melody(), str(tmp_path / "n.mid"),
                               style="piano", key="C", mode="major")
    assert r.key == "C" and r.mode == "major"
    assert not any("Modulated" in w for w in r.warnings)
