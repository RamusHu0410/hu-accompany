"""A hum-like WAV for tests that need one on disk."""

import wave

import numpy as np

# A short tune (MIDI note, seconds): C D E C, then E F G
TUNE = [(60, 0.4), (62, 0.4), (64, 0.4), (60, 0.4), (64, 0.4), (65, 0.4), (67, 0.8)]


def write_hum(path, tune=TUNE, rate=22050) -> None:
    """A hum-like WAV: each note a soft tone with a few overtones, with short gaps between notes."""
    pieces = []
    for midi, seconds in tune:
        t = np.arange(int(seconds * rate)) / rate
        hz = 440.0 * 2 ** ((midi - 69) / 12)
        tone = sum(np.sin(2 * np.pi * hz * k * t) / k for k in (1, 2, 3))
        fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.03)
        pieces += [0.3 * tone * fade, np.zeros(int(0.12 * rate))]
    samples = (np.concatenate(pieces) * 32767 / 1.8).astype(np.int16)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())
