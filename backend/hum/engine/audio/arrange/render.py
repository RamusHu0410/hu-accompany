"""Arrangement MIDI -> audio, with FluidSynth and a General MIDI soundfont.

The fluidsynth command-line tool is used when it's installed: it renders in stereo, straight to
32-bit float at the rate we ask for. Otherwise `pretty_midi.PrettyMIDI.fluidsynth()` (through
pyfluidsynth) is the fallback, but that one returns mono (it keeps every other sample). FluidSynth's
own reverb and chorus are off: the effects step adds reverb.

The render is gain-staged to a -3 dBFS peak, so the effects chain always gets the same level,
and its trailing near-silence is trimmed (FluidSynth keeps rendering until every voice has died
away), so the reverb tail the effects add follows the music instead of seconds of dead air.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from .config import SAMPLE_RATE, find_soundfont
from .files import write_atomically
from .validate import ValidationError, check_audio, validate_audio

logger = logging.getLogger(__name__)

RENDER_PEAK = 10 ** (-3 / 20)  # -3 dBFS
FLUIDSYNTH_GAIN = 0.5
TRIM_BELOW = 10 ** (-60 / 20)  # trailing audio quieter than -60 dBFS (after gain staging) is cut
TRIM_MARGIN_SECONDS = 0.25


def synthesize(midi_path: str | Path, soundfont: str | Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """(samples, channels) float32 audio of `midi_path`, unnormalized."""
    if shutil.which("fluidsynth"):
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch) / "render.wav"
            command = [
                "fluidsynth", "-ni", "-q",
                "-R", "0", "-C", "0",  # no built-in reverb/chorus
                "-g", str(FLUIDSYNTH_GAIN),
                "-r", str(sample_rate),
                "-O", "float", "-T", "wav",
                "-F", str(out),
                str(soundfont), str(midi_path),
            ]
            logger.debug("render: %s", " ".join(command))
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            if result.returncode != 0 or not out.is_file():
                raise RuntimeError(f"fluidsynth failed (exit {result.returncode}): {result.stderr.strip()[:500]}")
            audio, rate = sf.read(str(out), dtype="float32", always_2d=True)
            if rate != sample_rate:
                raise RuntimeError(f"fluidsynth rendered at {rate} Hz instead of {sample_rate} Hz.")
            return audio

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    mono = midi.fluidsynth(fs=sample_rate, synthesizer=str(soundfont))
    return mono.astype(np.float32)[:, np.newaxis]


def trim_tail(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """`audio` (samples, channels) without its trailing near-silence, keeping a short margin."""
    loud = np.flatnonzero(np.max(np.abs(audio), axis=1) > TRIM_BELOW)
    if loud.size == 0:
        return audio
    end = min(len(audio), int(loud[-1]) + 1 + int(TRIM_MARGIN_SECONDS * sample_rate))
    return audio[:end]


def render(midi_path: str | Path, wav_path: str | Path, soundfont: str | Path | None = None,
           sample_rate: int = SAMPLE_RATE) -> Path:
    """Render to a new 32-bit float WAV at `sample_rate`, peaking at -3 dBFS."""
    soundfont = Path(soundfont) if soundfont else find_soundfont()
    audio = synthesize(midi_path, soundfont, sample_rate)
    if audio.size == 0 or not np.all(np.isfinite(audio)):
        raise ValidationError("The render is empty or has NaN/Inf samples.")
    peak = float(np.max(np.abs(audio)))
    if peak <= 0:
        raise ValidationError("The render is silent.")
    raw_seconds = len(audio) / sample_rate
    audio = trim_tail(audio * (RENDER_PEAK / peak), sample_rate)
    logger.debug("render: %s, %.2f s (trimmed from %.2f s), %d ch, raw peak %.3f -> normalized to -3 dBFS",
                 Path(soundfont).name, len(audio) / sample_rate, raw_seconds, audio.shape[1], peak)
    check_audio(audio, where="render")

    def write(tmp: Path) -> None:
        sf.write(str(tmp), audio, sample_rate, subtype="FLOAT")

    return write_atomically(wav_path, write, lambda p: validate_audio(p, sample_rate=sample_rate, subtype="FLOAT"))
