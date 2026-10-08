"""Rendered audio -> the final 24-bit WAV, through a per-style Pedalboard chain:
Compressor -> LowShelfFilter -> Reverb -> Limiter (settings in config.STYLES).

pedalboard is optional. Its native library needs system libraries (libatomic.so.1, libX11) that
some hosts don't ship -- Vercel's Python runtime is one, where importing it took down the whole app
at startup. When it's missing, apply_effects raises and steps.py falls back to
copy_without_effects, so the song is still written, just without the effects chain. Reading and
writing go through soundfile (a dependency either way), so the fallback needs no pedalboard at all.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

try:
    from pedalboard import Compressor, Limiter, LowShelfFilter, Pedalboard, Reverb
except Exception as exc:  # noqa: BLE001 - ImportError here, but a missing .so can raise OSError
    Pedalboard = None
    _PEDALBOARD_UNAVAILABLE: Exception | None = exc
else:
    _PEDALBOARD_UNAVAILABLE = None

from .config import Effects
from .files import write_atomically
from .validate import check_audio, validate_audio

logger = logging.getLogger(__name__)

# Every final.wav peaks here: the same 0.9 peak the app's other songs are normalized to, so
# versions play equally loud (and 24-bit rounding can never reach 1.0).
OUTPUT_CEILING = 0.9
INPUT_PEAK = 10 ** (-6 / 20)  # the chain's thresholds assume input peaking at -6 dBFS


def build_chain(settings: Effects) -> Pedalboard:
    if Pedalboard is None:
        raise RuntimeError(f"pedalboard isn't usable on this host: {_PEDALBOARD_UNAVAILABLE}")
    return Pedalboard([
        Compressor(
            threshold_db=settings.compressor_threshold_db,
            ratio=settings.compressor_ratio,
            attack_ms=settings.compressor_attack_ms,
            release_ms=settings.compressor_release_ms,
        ),
        LowShelfFilter(cutoff_frequency_hz=settings.low_shelf_hz, gain_db=settings.low_shelf_gain_db),
        Reverb(
            room_size=settings.reverb_room_size,
            damping=settings.reverb_damping,
            wet_level=settings.reverb_wet,
            dry_level=settings.reverb_dry,
            width=settings.reverb_width,
        ),
        Limiter(threshold_db=settings.limiter_threshold_db, release_ms=settings.limiter_release_ms),
    ])


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """(channels, samples) float32 and the sample rate, as Pedalboard wants it."""
    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    # soundfile gives (samples, channels); transpose, and make it contiguous for the chain.
    return np.ascontiguousarray(audio.T), int(sample_rate)


def _safe_level(audio: np.ndarray) -> np.ndarray:
    """Peak-normalized to OUTPUT_CEILING."""
    peak = float(np.max(np.abs(audio)))
    return audio * (OUTPUT_CEILING / peak) if peak > 0 else audio


def write_24bit(audio: np.ndarray, sample_rate: int, path: str | Path) -> Path:
    """A new 24-bit WAV of (channels, samples) audio, validated before it takes its name."""
    audio = _safe_level(audio.astype(np.float32))
    check_audio(audio, where="final audio")

    def write(tmp: Path) -> None:
        sf.write(str(tmp), audio.T, sample_rate, subtype="PCM_24")

    return write_atomically(path, write, lambda p: validate_audio(p, sample_rate=sample_rate, subtype="PCM_24"))


def apply_effects(in_path: str | Path, out_path: str | Path, settings: Effects) -> Path:
    """The style's chain over the rendered audio, with room for the reverb tail, as 24-bit."""
    audio, sample_rate = read_audio(in_path)
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio * (INPUT_PEAK / peak)
    tail = np.zeros((audio.shape[0], int(settings.tail_seconds * sample_rate)), dtype=np.float32)
    chain = build_chain(settings)
    logger.debug("effects: %s", " -> ".join(type(plugin).__name__ for plugin in chain))
    logger.debug("  %s", settings)
    processed = chain(np.concatenate([audio, tail], axis=1), sample_rate)
    logger.debug("  peak in %.3f, out %.3f (before the safety ceiling), %.2f s with the %.1f s tail",
                 float(np.max(np.abs(audio))), float(np.max(np.abs(processed))), processed.shape[1] / sample_rate, settings.tail_seconds)
    if not np.all(np.isfinite(processed)):
        raise ValueError("The effects chain produced NaN/Inf samples.")
    return write_24bit(processed, sample_rate, out_path)


def copy_without_effects(in_path: str | Path, out_path: str | Path) -> Path:
    """The fallback final: the rendered audio as it is, just written as 24-bit."""
    audio, sample_rate = read_audio(in_path)
    return write_24bit(audio, sample_rate, out_path)
