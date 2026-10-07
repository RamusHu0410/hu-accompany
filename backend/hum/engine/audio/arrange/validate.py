"""Checks every output must pass before it's allowed to take its name."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

# Quieter than this over the whole file counts as silent: -80 dBFS RMS, far below any real music.
SILENCE_RMS = 1e-4


class ValidationError(ValueError):
    """An output file is unusable (unreadable, empty, silent, clipping...)."""


def validate_midi(path: str | Path, min_tracks: int = 1, music21: bool = False) -> pretty_midi.PrettyMIDI:
    """The MIDI parses (with pretty_midi, and with music21's converter too if `music21`), has at
    least `min_tracks` tracks with notes, and those notes are sane."""
    try:
        midi = pretty_midi.PrettyMIDI(str(path))
        if music21:
            from music21 import converter

            if not converter.parse(str(path)).flatten().notes:
                raise ValidationError("music21 reads no notes in it.")
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 - any parse failure means the file is bad
        raise ValidationError(f"MIDI doesn't parse: {exc}") from exc
    with_notes = [inst for inst in midi.instruments if inst.notes]
    if len(with_notes) < min_tracks:
        raise ValidationError(f"MIDI has {len(with_notes)} track(s) with notes, needs {min_tracks}.")
    for inst in with_notes:
        for note in inst.notes:
            if not 0 <= note.pitch <= 127 or not 1 <= note.velocity <= 127 or note.end <= note.start:
                raise ValidationError(f"Bad note in track '{inst.name}': {note}.")
    return midi


def check_audio(audio: np.ndarray, where: str = "audio") -> None:
    """No NaN/Inf, not silent, peak ≤ 1.0. `audio` is any shape of samples."""
    if audio.size == 0:
        raise ValidationError(f"{where} is empty.")
    if not np.all(np.isfinite(audio)):
        raise ValidationError(f"{where} contains NaN or Inf samples.")
    peak = float(np.max(np.abs(audio)))
    if peak > 1.0:
        raise ValidationError(f"{where} clips: peak {peak:.4f} > 1.0.")
    rms = math.sqrt(float(np.mean(np.square(audio, dtype=np.float64))))
    if rms < SILENCE_RMS:
        raise ValidationError(f"{where} is silent (RMS {rms:.2e}).")


def validate_audio(
    path: str | Path,
    *,
    sample_rate: int | None = None,
    subtype: str | None = None,
) -> sf._SoundFileInfo:
    """The file opens as audio (at `sample_rate`, stored as `subtype`, e.g. "PCM_24") and its
    samples pass `check_audio`."""
    try:
        info = sf.info(str(path))
        audio, _ = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Audio doesn't open: {exc}") from exc
    if sample_rate is not None and info.samplerate != sample_rate:
        raise ValidationError(f"Sample rate is {info.samplerate}, expected {sample_rate}.")
    if subtype is not None and info.subtype != subtype:
        raise ValidationError(f"Stored as {info.subtype}, expected {subtype}.")
    check_audio(audio, where=Path(path).name)
    return info
