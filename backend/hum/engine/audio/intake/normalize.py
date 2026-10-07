"""The recording as it came, kept untouched, and a clean working copy of it.

The original is copied into the run directory, made read-only and fingerprinted (SHA-256); every
later step works on intake_normalized.wav instead: mono, silent ends trimmed, loudest moment at -1 dBFS.
Both are named intake_*, so they can't collide with the arrangement step's files.
WAV, FLAC and Ogg are read with soundfile; anything else (Chrome's webm, Safari's mp4) with PyAV.
"""

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass, field

import av
import librosa
import numpy as np
import soundfile as sf

from .config import AUDIO, AudioSettings
from ..errors import PipelineError

STEP = "intake.normalize"
ORIGINAL_STEM = "intake_original"
NORMALIZED_NAME = "intake_normalized.wav"


@dataclass
class Normalized:
    path: str  # the working copy, intake_normalized.wav
    original_path: str  # the untouched, read-only copy of the upload
    sha256: str  # the upload's fingerprint, before and after
    sample_rate: int
    seconds: float
    channels: int  # in the original
    warnings: list[str] = field(default_factory=list)


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def keep_original(input_path: str, run_dir: str) -> tuple[str, str]:
    """A read-only copy of the upload in run_dir, and its SHA-256. Never overwrites a file."""
    if not os.path.isfile(input_path):
        raise PipelineError(STEP, "The recording wasn't found.", code="not_found")
    checksum = sha256_of(input_path)
    extension = os.path.splitext(input_path)[1].lower() or ".bin"
    copy = new_file(run_dir, ORIGINAL_STEM + extension)
    shutil.copyfile(input_path, copy)
    os.chmod(copy, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    if sha256_of(copy) != checksum:
        raise PipelineError(STEP, "The recording couldn't be copied safely. Try again.", code="copy_failed")
    return copy, checksum


def normalize(original_path: str, checksum: str, run_dir: str, settings: AudioSettings = AUDIO) -> Normalized:
    """Reads the copy, checks it's a usable hum, and writes the working copy intake_normalized.wav."""
    samples, rate = read_audio(original_path)  # (frames, channels)
    if samples.size == 0:
        raise PipelineError(STEP, "The recording is empty.", code="empty")
    channels = samples.shape[1]
    mono = samples.mean(axis=1)
    warnings = []

    peak = float(np.max(np.abs(mono)))
    if not np.isfinite(peak) or peak < settings.silence_peak:
        raise PipelineError(STEP, "The recording is silent. Check the microphone and hum a little louder.", code="silent")
    if np.mean(np.abs(samples) >= settings.clip_level) > settings.clip_share:
        warnings.append("The recording was too loud and clipped, so some notes may be off. Hum a little further from the mic.")

    _, (start, end) = librosa.effects.trim(mono, top_db=settings.trim_top_db)
    pad = int(rate * settings.trim_pad_ms / 1000)
    mono = mono[max(0, start - pad) : min(len(mono), end + pad)]
    seconds = len(mono) / rate
    if seconds < settings.min_seconds:
        raise PipelineError(STEP, f"The recording is too short ({seconds:.1f} s). Hum for at least a second.", code="too_short")
    if seconds > settings.max_seconds:
        raise PipelineError(STEP, f"The recording is too long ({seconds:.0f} s). Keep it under {settings.max_seconds:.0f} s.", code="too_long")

    mono = mono * (settings.peak_level / np.max(np.abs(mono)))
    path = new_file(run_dir, NORMALIZED_NAME)
    sf.write(path, mono.astype(np.float32), rate, subtype="PCM_16")
    return Normalized(path, original_path, checksum, rate, seconds, channels, warnings)


def read_audio(path: str) -> tuple[np.ndarray, int]:
    """Samples as float (frames, channels) and the sample rate, or a PipelineError if it isn't audio."""
    try:
        samples, rate = sf.read(path, dtype="float32", always_2d=True)
        return samples, rate
    except (sf.LibsndfileError, RuntimeError):
        pass  # not a format soundfile knows: try PyAV (webm, mp4, ...)
    try:
        return _read_with_av(path)
    except (av.error.FFmpegError, ValueError, IndexError) as exc:
        raise PipelineError(STEP, "That file isn't a recording we can read. Record your hum again.", code="unreadable") from exc


def _read_with_av(path: str) -> tuple[np.ndarray, int]:
    with av.open(path) as container:
        stream = container.streams.audio[0]  # IndexError: no audio in it
        rate = stream.codec_context.sample_rate
        resampler = av.AudioResampler(format="fltp", layout=stream.layout.name, rate=rate)
        chunks = [chunk.to_ndarray() for frame in container.decode(stream) for chunk in resampler.resample(frame)]
    if not chunks:
        return np.zeros((0, 1), dtype=np.float32), rate
    return np.concatenate(chunks, axis=1).T, rate


def new_file(run_dir: str, name: str, step: str = STEP) -> str:
    """A path in run_dir for a file a step creates. Every step writes new files; none overwrites."""
    path = os.path.join(run_dir, name)
    if os.path.exists(path):
        raise PipelineError(step, f"{name} already exists in the run directory; each run needs its own.", code="exists")
    return path
