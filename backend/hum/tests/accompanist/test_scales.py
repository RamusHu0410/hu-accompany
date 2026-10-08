"""Tests for scale snapping and scale-flavored styles (jazz, asian_folk)."""

import pretty_midi

from hum.engine.accompanist.music.scales import (
    snap_pitch,
    snap_notes,
    scale_pitch_classes,
    SCALES,
)
from hum.engine.accompanist.music.styles import STYLES, STYLE_SCALES
from hum.engine.accompanist.generate import generate_accompaniment


# ---------------------------------------------------------------------------
# scale definitions & snapping
# ---------------------------------------------------------------------------

def test_scales_registered():
    assert {"jazz", "blues", "pentatonic"} <= set(SCALES)
    assert STYLE_SCALES["jazz"] == "jazz"
    assert STYLE_SCALES["asian_folk"] == "pentatonic"


def test_c_pentatonic_pitch_classes():
    # C major pentatonic = C D E G A = {0,2,4,7,9}
    assert scale_pitch_classes("C", "pentatonic") == {0, 2, 4, 7, 9}


def test_in_scale_pitch_unchanged():
    # E (64) is in C pentatonic -> unchanged.
    assert snap_pitch(64, "C", "pentatonic") == 64


def test_out_of_scale_pitch_snaps():
    # F (65) and F# (66) are NOT in C pentatonic; both snap to a scale tone.
    snapped_f = snap_pitch(65, "C", "pentatonic")
    snapped_fs = snap_pitch(66, "C", "pentatonic")
    assert snapped_f % 12 in scale_pitch_classes("C", "pentatonic")
    assert snapped_fs % 12 in scale_pitch_classes("C", "pentatonic")


def test_snap_is_nearest():
    # F#4 (66) should snap to G4 (67), the nearest pentatonic tone.
    assert snap_pitch(66, "C", "pentatonic") == 67


def test_snap_notes_preserves_timing():
    notes = [{"pitch": 66, "start": 0, "duration": 1}]  # F#
    out = snap_notes(notes, "C", "pentatonic")
    assert out[0]["start"] == 0
    assert out[0]["duration"] == 1
    assert out[0]["pitch"] % 12 in scale_pitch_classes("C", "pentatonic")


def test_all_snapped_notes_in_scale():
    chromatic = [{"pitch": p, "start": i, "duration": 1}
                 for i, p in enumerate(range(60, 73))]
    for scale in ("jazz", "pentatonic"):
        out = snap_notes(chromatic, "C", scale)
        allowed = scale_pitch_classes("C", scale)
        assert all(n["pitch"] % 12 in allowed for n in out)


# ---------------------------------------------------------------------------
# scale-flavored styles end to end
# ---------------------------------------------------------------------------

def _melody_with_chromatics():
    bar_notes = {
        0: [60, 61, 64, 66], 1: [65, 68, 72, 70], 2: [67, 71, 73, 67],
        3: [72, 66, 64, 61], 4: [69, 72, 75, 69], 5: [65, 68, 72, 65],
        6: [67, 70, 74, 71], 7: [60, 63, 67, 60],
    }
    notes = []
    for bar, ps in bar_notes.items():
        for beat, p in enumerate(ps):
            notes.append({"hz": p, "start": bar * 4 + beat, "duration": 1.0})
    return {"melody": notes, "tempo": 120}


def test_jazz_and_asian_folk_registered():
    assert "jazz" in STYLES
    assert "asian_folk" in STYLES


def test_jazz_generation_snaps_melody(tmp_path):
    out = tmp_path / "jazz.mid"
    result = generate_accompaniment(
        _melody_with_chromatics(), str(out), style="jazz", key="C", mode="major",
        allow_edit_melody=True,
    )
    # Melody track written; every melody pitch is now in the jazz scale.
    pm = pretty_midi.PrettyMIDI(str(out))
    assert len(pm.instruments) == 2
    allowed = scale_pitch_classes("C", "jazz")
    melody_track = pm.instruments[1]
    assert all(n.pitch % 12 in allowed for n in melody_track.notes)
    assert any("jazz" in w for w in result.warnings)


def test_asian_folk_generation_snaps_melody(tmp_path):
    out = tmp_path / "folk.mid"
    result = generate_accompaniment(
        _melody_with_chromatics(), str(out), style="asian_folk",
        key="C", mode="major", allow_edit_melody=True,
    )
    pm = pretty_midi.PrettyMIDI(str(out))
    allowed = scale_pitch_classes("C", "pentatonic")
    melody_track = pm.instruments[1]
    assert all(n.pitch % 12 in allowed for n in melody_track.notes)


def test_non_scale_style_does_not_snap(tmp_path):
    # A regular style should leave out-of-scale notes untouched.
    out = tmp_path / "piano.mid"
    result = generate_accompaniment(
        _melody_with_chromatics(), str(out), style="piano", key="C", mode="major"
    )
    pm = pretty_midi.PrettyMIDI(str(out))
    melody_track = pm.instruments[1]
    # F# (pc 6) is present in the input and should survive (not pentatonic-snapped).
    pcs = {n.pitch % 12 for n in melody_track.notes}
    assert 6 in pcs or 1 in pcs  # a chromatic pitch class remains
    assert not any("snapped" in w for w in result.warnings)
