"""Render MIDI files to audio (WAV) using FluidSynth."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# Where we look for a soundfont, in priority order.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # hum/engine/accompanist
_DEFAULT_SOUNDFONT_CANDIDATES = [
    _PROJECT_ROOT / "soundfonts" / "FluidR3_GM.sf2",
    Path("/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2"),
    Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
    Path("/usr/local/share/fluidsynth/FluidR3_GM.sf2"),
]

DEFAULT_SAMPLE_RATE = 44100


def find_soundfont() -> str:
    """Locate a usable .sf2 soundfont.

    Honors the ECKO_SOUNDFONT environment variable if set, otherwise falls
    back to a list of known locations.
    """
    env = os.environ.get("ECKO_SOUNDFONT")
    if env and Path(env).is_file():
        return env
    for candidate in _DEFAULT_SOUNDFONT_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        "No soundfont (.sf2) found. Set ECKO_SOUNDFONT or place one at "
        f"{_DEFAULT_SOUNDFONT_CANDIDATES[0]}"
    )


def render_midi(
    midi_path: str,
    wav_path: str,
    *,
    soundfont: str | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> str:
    """Render a MIDI file to a WAV file using FluidSynth.

    Args:
        midi_path: Path to the input .mid file.
        wav_path: Path for the output .wav file.
        soundfont: Path to a .sf2 soundfont. If None, one is auto-discovered.
        sample_rate: Output sample rate in Hz.

    Returns:
        The path the WAV was written to.

    Raises:
        FileNotFoundError: if fluidsynth, the MIDI, or a soundfont is missing.
        RuntimeError: if fluidsynth fails or produces no output.
    """
    if shutil.which("fluidsynth") is None:
        raise FileNotFoundError(
            "fluidsynth executable not found on PATH. Install it (e.g. "
            "`brew install fluid-synth`)."
        )
    if not Path(midi_path).is_file():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    sf2 = soundfont or find_soundfont()

    cmd = [
        "fluidsynth",
        "-ni",  # no shell, no MIDI input device
        "-F", wav_path,  # render to this file
        "-r", str(sample_rate),
        sf2,
        midi_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"fluidsynth failed (exit {result.returncode}):\n{result.stderr}"
        )
    if not Path(wav_path).is_file() or Path(wav_path).stat().st_size == 0:
        raise RuntimeError("fluidsynth ran but produced no WAV output.")

    return wav_path
