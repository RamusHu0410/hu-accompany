"""End-to-end tests for the full generation pipeline (Phase 18)."""

import json

import pretty_midi
import pytest

from hum.engine.accompanist.generate import generate_accompaniment, AccompanimentResult
from hum.engine.accompanist.models.melody import Melody


KINGSLEY_JSON = json.dumps(
    {
        "melody": [
            {"hz": 60, "start": 0, "duration": 0.5},
            {"hz": 64, "start": 0.5, "duration": 0.5},
            {"hz": 67, "start": 1, "duration": 1},
        ],
        "key": "C",
        "mode": "major",
        "tempo": 100,
    }
)


def _eight_bar_melody_dict():
    bar_notes = {
        0: [60, 64, 67, 72], 1: [65, 69, 72, 69], 2: [67, 71, 74, 67],
        3: [72, 67, 64, 60], 4: [69, 72, 76, 69], 5: [65, 69, 72, 65],
        6: [67, 71, 74, 71], 7: [60, 64, 67, 60],
    }
    notes = []
    for bar, ps in bar_notes.items():
        for beat, p in enumerate(ps):
            notes.append({"hz": p, "start": bar * 4 + beat, "duration": 1.0})
    return {"melody": notes, "tempo": 120}


def test_generate_from_json_string(tmp_path):
    out = tmp_path / "k.mid"
    result = generate_accompaniment(KINGSLEY_JSON, str(out), style="piano")
    assert isinstance(result, AccompanimentResult)
    assert result.key == "C"
    assert result.mode == "major"
    assert out.is_file()
    assert len(result.progression) >= 1


def test_generate_from_dict(tmp_path):
    out = tmp_path / "d.mid"
    result = generate_accompaniment(
        {"melody": [{"hz": 60, "start": 0, "duration": 1}], "tempo": 120},
        str(out),
    )
    assert out.is_file()


def test_generate_from_melody_object(tmp_path):
    mel = Melody.from_dict(json.loads(KINGSLEY_JSON))
    out = tmp_path / "m.mid"
    result = generate_accompaniment(mel, str(out))
    assert out.is_file()


def test_eight_bar_progression(tmp_path):
    out = tmp_path / "8.mid"
    result = generate_accompaniment(
        _eight_bar_melody_dict(), str(out), style="classical"
    )
    assert result.progression_symbols == ["C", "F", "G", "C", "Am", "F", "G", "C"]
    # Progression stays diatonic in C major.
    diatonic = {"C", "Dm", "Em", "F", "G", "Am", "Bdim"}
    assert all(s in diatonic for s in result.progression_symbols)


def test_key_autodetected_without_metadata(tmp_path):
    # No key/mode in the input -> must be detected.
    out = tmp_path / "auto.mid"
    result = generate_accompaniment(_eight_bar_melody_dict(), str(out))
    assert result.key == "C"
    assert result.mode == "major"


def test_key_override(tmp_path):
    out = tmp_path / "ov.mid"
    result = generate_accompaniment(
        _eight_bar_melody_dict(), str(out), key="G", mode="major"
    )
    assert result.key == "G"
    # All chords should now be diatonic to G major.
    diatonic = {"G", "Am", "Bm", "C", "D", "Em", "F#dim"}
    assert all(s in diatonic for s in result.progression_symbols)


def test_all_styles_run(tmp_path):
    for style in ("piano", "pop", "cinematic", "classical"):
        out = tmp_path / f"{style}.mid"
        result = generate_accompaniment(
            _eight_bar_melody_dict(), str(out), style=style
        )
        pm = pretty_midi.PrettyMIDI(str(out))
        assert len(pm.instruments[0].notes) > 0


def test_unknown_style_raises(tmp_path):
    with pytest.raises(ValueError):
        generate_accompaniment(KINGSLEY_JSON, str(tmp_path / "x.mid"),
                               style="reggae")


def test_melody_track_included_and_excluded(tmp_path):
    with_mel = tmp_path / "with.mid"
    without_mel = tmp_path / "without.mid"
    generate_accompaniment(_eight_bar_melody_dict(), str(with_mel),
                           include_melody=True)
    generate_accompaniment(_eight_bar_melody_dict(), str(without_mel),
                           include_melody=False)
    assert len(pretty_midi.PrettyMIDI(str(with_mel)).instruments) == 2
    assert len(pretty_midi.PrettyMIDI(str(without_mel)).instruments) == 1
