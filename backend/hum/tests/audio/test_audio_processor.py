import wave
from pathlib import Path

import pytest
import numpy as np
from hum.engine.audio.processor import (
    AudioProcessor,
    analyze_audio_file,
    quick_analyze,
    extract_notes,
    load_and_process_wav,
    _estimate_key_and_mode,
    _estimate_tempo,
    _build_melody,
)

FIXTURE_WAV = str(Path(__file__).parent.parent / "fixtures" / "test.wav")


def _write_silent_wav(path, seconds=1.0, sample_rate=22050):
    """A minimal valid mono 16-bit WAV, for tests that just need a real file to load."""
    n_frames = int(seconds * sample_rate)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)


def test_audio_processor_init():
    processor = AudioProcessor()
    assert processor is not None
    assert hasattr(processor, "target_sr")


def test_audio_processor_init_with_custom_params():
    processor = AudioProcessor(target_sr=44100, hop_length=1024, frame_length=4096)
    assert processor.target_sr == 44100
    assert processor.hop_length == 1024
    assert processor.frame_length == 4096


def test_estimate_key_and_mode():
    audio = np.zeros(22050)
    key, mode = _estimate_key_and_mode(audio, 22050)
    assert isinstance(key, str)
    assert isinstance(mode, str)


def test_estimate_tempo():
    audio = np.zeros(22050)
    tempo = _estimate_tempo(audio, 22050)
    assert isinstance(tempo, float)


def test_build_melody():
    analysis = {
        "segments": [],
        "pitch": [],
        "volume": [],
        "spectral": {},
    }
    melody = _build_melody(analysis)
    assert isinstance(melody, list)


def test_quick_analyze():
    result = quick_analyze(FIXTURE_WAV)
    assert isinstance(result, dict)


def test_load_and_process_wav(tmp_path):
    wav_path = tmp_path / "test.wav"
    _write_silent_wav(wav_path)
    result = load_and_process_wav(str(wav_path))
    assert isinstance(result, dict)


def test_extract_notes():
    notes = extract_notes(FIXTURE_WAV)
    assert isinstance(notes, list)
