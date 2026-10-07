"""Recordings that aren't clean: every one either works or fails with a clear reason, and the
original file is never changed."""

import json
import os

import av
import numpy as np
import pytest
import soundfile as sf

from hum.engine.audio.intake import PipelineError, transcribe_to_melody
from hum.engine.audio.intake.normalize import sha256_of

from .hum_synth import Sung, hum, write

TUNE = [Sung(50, 0, 1), Sung(52, 1, 1), Sung(53, 2, 2)]
PITCHES = [50, 52, 53]


def _pitches(result):
    with open(result.json_path) as file:
        return [n["pitch"] for n in json.load(file)["notes"]]


def _refused(source, run_dir, code, says):
    before = sha256_of(source)
    with pytest.raises(PipelineError) as refused:
        transcribe_to_melody(str(source), str(run_dir))
    assert refused.value.code == code
    assert says in refused.value.message
    assert refused.value.step.startswith("intake")
    assert sha256_of(source) == before  # the original is untouched
    with open(run_dir / "intake_log.json") as file:
        assert json.load(file)["error"] == {"step": refused.value.step, "code": code, "message": refused.value.message}


def test_a_corrupt_file_is_refused_clearly(tmp_path):
    source = tmp_path / "hum.wav"
    source.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + os.urandom(2000))
    _refused(source, tmp_path / "run", "unreadable", "isn't a recording we can read")


def test_an_empty_file_is_refused_clearly(tmp_path):
    source = tmp_path / "hum.wav"
    source.write_bytes(b"")
    _refused(source, tmp_path / "run", "unreadable", "isn't a recording we can read")


def test_a_silent_recording_is_refused_clearly(tmp_path):
    source = write(tmp_path / "hum.wav", np.zeros(44100 * 3, dtype=np.float32))
    _refused(source, tmp_path / "run", "silent", "silent")


def test_a_stereo_recording_is_mixed_down(tmp_path):
    mono = hum(TUNE, tempo=120)
    source = tmp_path / "hum.wav"
    sf.write(source, np.stack([mono, 0.6 * mono], axis=1), 44100, subtype="PCM_16")
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert _pitches(result) == PITCHES


def test_a_webm_recording_from_chrome_is_converted(tmp_path):
    source = tmp_path / "hum.webm"
    _write_webm(source, hum(TUNE, tempo=120, rate=48000))
    before = sha256_of(source)
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert _pitches(result) == PITCHES
    assert sha256_of(source) == before and os.path.exists(tmp_path / "run" / "intake_original.webm")


def test_an_ogg_recording_is_converted(tmp_path):
    source = tmp_path / "hum.ogg"
    sf.write(source, hum(TUNE, tempo=120), 44100, format="OGG", subtype="VORBIS")
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert _pitches(result) == PITCHES


def test_a_clipped_recording_works_with_a_warning(tmp_path):
    source = write(tmp_path / "hum.wav", np.clip(hum(TUNE, tempo=120) * 4, -1, 1))
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert _pitches(result) == PITCHES
    assert any("clipped" in warning for warning in result.warnings)


def test_two_voices_at_once_give_a_warning(tmp_path):
    low = hum([Sung(50, 0, 4)], tempo=120)
    high = hum([Sung(56, 0, 4)], tempo=120, seed=3)  # a tritone above: not a harmonic of the low voice
    source = write(tmp_path / "hum.wav", 0.5 * low + 0.5 * high)
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert any("more than one voice" in warning for warning in result.warnings)


def test_a_run_never_overwrites_an_earlier_one(tmp_path):
    source = write(tmp_path / "hum.wav", hum(TUNE, tempo=120))
    first = transcribe_to_melody(str(source), str(tmp_path / "run"))
    written = sha256_of(first.json_path)
    with pytest.raises(PipelineError, match="already exists") as refused:
        transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert refused.value.code == "exists"
    assert sha256_of(first.json_path) == written


def test_a_tune_too_short_to_find_a_tempo_says_so(tmp_path):
    source = write(tmp_path / "hum.wav", hum([Sung(50, 0, 2), Sung(53, 2, 2)], tempo=120))
    result = transcribe_to_melody(str(source), str(tmp_path / "run"))
    assert _pitches(result) == [50, 53]
    assert any("too short to find its tempo" in warning for warning in result.warnings)


def test_a_tune_longer_than_16_bars_is_refused(tmp_path):
    long_tune = [Sung(50 + (i % 4), i, 1) for i in range(72)]  # 72 beats: 18 bars
    source = write(tmp_path / "hum.wav", hum(long_tune, tempo=120))
    _refused(source, tmp_path / "run", "too_long", "too long to make into a song")


def _write_webm(path, samples, rate=48000):
    """Opus in WebM, what Chrome's MediaRecorder makes."""
    with av.open(str(path), "w", format="webm") as container:
        stream = container.add_stream("libopus", rate=rate, layout="mono")
        size = 960
        for start in range(0, len(samples), size):
            chunk = np.zeros((1, size), dtype=np.float32)
            piece = samples[start : start + size]
            chunk[0, : len(piece)] = piece
            frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="mono")
            frame.sample_rate, frame.pts = rate, start
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
