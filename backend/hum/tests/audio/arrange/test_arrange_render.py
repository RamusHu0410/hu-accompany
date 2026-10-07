"""A real render of the fixture (FluidSynth + soundfont + Pedalboard), and the audio checks."""

import numpy as np
import pytest
import soundfile as sf

from hum.engine.audio.arrange import arrange_and_render
from hum.engine.audio.arrange.config import SAMPLE_RATE
from hum.engine.audio.arrange.validate import ValidationError, check_audio, validate_audio

from conftest import FIXTURE_JSON


@pytest.fixture(scope="module")
def rendered(tmp_path_factory, soundfont):
    run_dir = tmp_path_factory.mktemp("render")
    return run_dir, arrange_and_render(str(FIXTURE_JSON), "cinematic", str(run_dir))


def test_final_is_24_bit_stereo_at_the_render_rate(rendered):
    _, result = rendered
    info = sf.info(result.final_wav_path)
    assert (info.subtype, info.samplerate, info.channels) == ("PCM_24", SAMPLE_RATE, 2)
    assert result.fell_back is False and result.warnings == []


def test_final_is_not_silent_or_clipping(rendered):
    _, result = rendered
    audio, _ = sf.read(result.final_wav_path, dtype="float64")
    assert np.all(np.isfinite(audio))
    assert np.max(np.abs(audio)) == pytest.approx(0.9, abs=1e-3)  # every song peaks at 0.9
    assert np.sqrt(np.mean(audio ** 2)) > 0.01


def test_final_covers_the_whole_piece_plus_the_reverb_tail(rendered):
    _, result = rendered
    piece = 15 * 4 * 60 / 92  # 2-bar intro, the tune, its last phrase restated, a 1-bar ending: 15 bars at 92 bpm
    assert piece + 3 < result.duration_seconds < piece + 12


def test_every_step_kept_its_file(rendered):
    run_dir, result = rendered
    for name in ("melody.json", "melody_transformed.json", "melody_transformed.mid", "arrangement.mid", "rendered.wav", "final.wav"):
        assert (run_dir / name).is_file(), name
    assert sf.info(str(run_dir / "rendered.wav")).subtype == "FLOAT"
    assert [s.step for s in result.steps] == ["transform", "orchestrate", "render", "effects"]
    assert not list(run_dir.glob(".*tmp*")), "a temporary file was left behind"


def test_the_effects_changed_the_sound(rendered):
    run_dir, result = rendered
    dry, _ = sf.read(str(run_dir / "rendered.wav"))
    wet, _ = sf.read(result.final_wav_path)
    assert len(wet) > len(dry)  # the reverb tail
    assert np.max(np.abs(wet[len(dry):])) > 1e-3  # and there's reverb in it


@pytest.mark.parametrize("audio, message", [
    (np.zeros((48_000, 2)), "silent"),
    (np.array([[0.5, np.nan]]), "NaN"),
    (np.array([[1.2, 0.1]]), "clips"),
    (np.zeros((0, 2)), "empty"),
])
def test_bad_audio_is_refused(audio, message):
    with pytest.raises(ValidationError, match=message):
        check_audio(audio)


def test_validate_audio_checks_rate_and_bit_depth(tmp_path):
    path = tmp_path / "tone.wav"
    tone = 0.3 * np.sin(np.linspace(0, 440 * 2 * np.pi, 44_100))
    sf.write(str(path), tone, 44_100, subtype="PCM_16")
    with pytest.raises(ValidationError, match="Sample rate"):
        validate_audio(path, sample_rate=SAMPLE_RATE)
    with pytest.raises(ValidationError, match="PCM_24"):
        validate_audio(path, subtype="PCM_24")


def test_trailing_dead_air_is_trimmed_but_a_margin_kept():
    from hum.engine.audio.arrange.render import TRIM_MARGIN_SECONDS, trim_tail

    rate = 48_000
    tone = 0.5 * np.sin(np.linspace(0, 440 * 2 * np.pi, rate))[:, None].repeat(2, axis=1)
    audio = np.concatenate([tone, np.full((3 * rate, 2), 1e-5)])
    assert len(trim_tail(audio, rate)) == pytest.approx(rate + TRIM_MARGIN_SECONDS * rate, abs=2)
