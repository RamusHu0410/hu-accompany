"""Shared fixtures for the arrangement tests (app/audio/arrange, app/audio/pipeline.py)."""

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SRC = Path(__file__).resolve().parents[3]  # backend/hum

from hum.engine.audio.arrange import steps  # noqa: E402
from hum.engine.audio.arrange.config import SAMPLE_RATE, find_soundfont  # noqa: E402
from hum.engine.audio.arrange.files import write_atomically  # noqa: E402
from hum.engine.audio.arrange.melody import load_melody  # noqa: E402
from hum.engine.audio.arrange.validate import validate_audio  # noqa: E402

FIXTURES = SRC / "tests" / "fixtures"
FIXTURE_JSON = FIXTURES / "melody_sample.json"
FIXTURE_MIDI = FIXTURES / "melody_sample.mid"


@pytest.fixture
def melody():
    return load_melody(FIXTURE_JSON)


@pytest.fixture(scope="session")
def soundfont():
    """A real soundfont and fluidsynth, or skip: rendering tests need both."""
    try:
        path = find_soundfont()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    if shutil.which("fluidsynth") is None:
        pytest.skip("fluidsynth isn't installed")
    return path


def _sine_render(midi_path, wav_path, soundfont=None, sample_rate=SAMPLE_RATE):
    """Stands in for FluidSynth where a test is about the plumbing, not the sound: 2 s of stereo
    sine, written like the real render (atomically, 32-bit float, validated)."""
    t = np.arange(2 * sample_rate) / sample_rate
    tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    audio = np.stack([tone, tone], axis=1)
    return write_atomically(
        wav_path,
        lambda tmp: sf.write(str(tmp), audio, sample_rate, subtype="FLOAT"),
        lambda p: validate_audio(p, sample_rate=sample_rate, subtype="FLOAT"),
    )


@pytest.fixture
def fake_render(monkeypatch):
    monkeypatch.setattr(steps, "render", _sine_render)
