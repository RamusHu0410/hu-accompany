"""Tests for MIDI -> WAV rendering (Phase 3)."""

import shutil
import wave

import pytest

from hum.engine.accompanist.models.melody import Melody, Note
from hum.engine.accompanist.music.melody_to_midi import melody_to_midi
from hum.engine.accompanist.audio.render import render_midi, find_soundfont

_HAS_FLUIDSYNTH = shutil.which("fluidsynth") is not None


def _soundfont_available() -> bool:
    try:
        find_soundfont()
        return True
    except FileNotFoundError:
        return False


requires_synth = pytest.mark.skipif(
    not (_HAS_FLUIDSYNTH and _soundfont_available()),
    reason="fluidsynth and/or a soundfont are not available",
)


def make_melody() -> Melody:
    return Melody(
        notes=[
            Note(hz=60, start=0.0, duration=0.5),
            Note(hz=64, start=0.5, duration=0.5),
            Note(hz=67, start=1.0, duration=1.0),
        ],
        tempo=100,
    )


@requires_synth
def test_render_creates_wav(tmp_path):
    # Step 3.3 — test.mid -> test.wav
    mid = tmp_path / "test.mid"
    wav = tmp_path / "test.wav"
    melody_to_midi(make_melody(), str(mid))

    render_midi(str(mid), str(wav))

    assert wav.is_file()
    assert wav.stat().st_size > 0


@requires_synth
def test_rendered_wav_is_valid_audio(tmp_path):
    mid = tmp_path / "test.mid"
    wav = tmp_path / "test.wav"
    melody_to_midi(make_melody(), str(mid))
    render_midi(str(mid), str(wav))

    with wave.open(str(wav), "rb") as w:
        assert w.getnchannels() in (1, 2)
        assert w.getframerate() == 44100
        # There should be actual audio, roughly matching the 2s of notes.
        assert w.getnframes() > 0
