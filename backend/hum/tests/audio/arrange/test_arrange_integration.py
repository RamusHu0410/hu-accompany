"""Intake (part A) and arrangement (part B) together: part A's real output arranged in every style,
and a real hum through the whole pipeline."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from hum.engine.audio import pipeline
from hum.engine.audio.arrange import STYLES, arrange_and_render
from hum.engine.audio.arrange.melody import load_melody
from hum.engine.audio.errors import PipelineError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
HUM_WAV = FIXTURES / "hum_sample.wav"
HUM_MELODY = FIXTURES / "hum_sample.melody.json"


@pytest.mark.parametrize("style", sorted(STYLES))
def test_part_as_hum_sample_melody_arranges_in_every_style(style, tmp_path, fake_render):
    result = arrange_and_render(str(HUM_MELODY), style, str(tmp_path))
    assert result.fell_back is False and result.warnings == []
    transformed = load_melody(tmp_path / "melody_transformed.json")
    assert transformed.key == "D minor" and transformed.tempo_bpm == 92.2


def test_a_hum_through_the_whole_pipeline(tmp_path, soundfont):
    """hum_sample.wav -> part A's intake -> the arrangement -> final.wav (real FluidSynth)."""
    result = pipeline.run_pipeline(str(HUM_WAV), "piano", run_dir=str(tmp_path / "run"), intake="intake")
    run = Path(result.run_dir)

    for name in ("intake_normalized.wav", "melody_clean.mid", "melody.json", "intake_log.json",   # part A
                 "melody_transformed.json", "arrangement.mid", "rendered.wav", "final.wav",         # part B
                 "run.json"):
        assert (run / name).is_file(), name

    melody = load_melody(run / "melody.json")
    assert melody.key == "D minor" and len(melody.notes) == 11  # what part A's own test pins down
    assert result.melody.note_count == 11 and result.fell_back is False

    info = sf.info(result.final_wav_path)
    assert (info.subtype, info.samplerate, info.channels) == ("PCM_24", 48_000, 2)
    audio, _ = sf.read(result.final_wav_path)
    assert np.max(np.abs(audio)) == pytest.approx(0.9, abs=1e-3)
    song = load_melody(run / "melody_transformed.json")  # the tune, filled out and framed into a song
    song_seconds = song.bars * song.beats_per_bar * song.seconds_per_beat
    assert song.bars >= 8 + STYLES["piano"].intro_bars + STYLES["piano"].outro_bars
    assert song_seconds < result.duration_seconds < song_seconds + 5  # plus the piano style's reverb tail

    log = json.loads((run / "run.json").read_text())
    assert [s["step"] for s in log["steps"]] == ["intake", "transform", "orchestrate", "render", "effects"]
    assert log["intake"] == "intake" and log["status"] == "ok"


def test_an_intake_refusal_reaches_the_caller_with_its_step_and_code(tmp_path):
    silent = tmp_path / "silent.wav"
    sf.write(str(silent), np.zeros(44_100 * 2), 44_100)
    with pytest.raises(PipelineError) as caught:
        pipeline.run_pipeline(str(silent), "pop", run_dir=str(tmp_path / "run"), intake="intake")
    assert caught.value.step.startswith("intake")
    assert caught.value.code == "silent"
    log = json.loads((tmp_path / "run" / "run.json").read_text())
    assert log["status"] == "failed" and log["code"] == "silent"
    assert not (tmp_path / "run" / "final.wav").exists()
