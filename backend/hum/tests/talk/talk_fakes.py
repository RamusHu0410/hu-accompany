"""Stand-ins for Gemini and ElevenLabs, so the talk tests never touch the network, and a hum maker."""

import wave

import numpy as np

from hum.engine.talk.commands import Adjustment, Command
from hum.engine.talk.pipeline import Pipeline
from hum.engine.talk.services import Services
from hum.engine.talk.store import ShortTermStore

FASTER = Command(
    intent="adjust",
    adjustments=[Adjustment(setting="speed", direction="up", amount="moderate")],
    reply="A little quicker now!",
)
# A short tune (MIDI note, seconds): C D E C, then E F G
TUNE = [(60, 0.4), (62, 0.4), (64, 0.4), (60, 0.4), (64, 0.4), (65, 0.4), (67, 0.8)]


class FakeGemini:
    """Answers every command with the prepared Command and remembers what it was asked."""

    def __init__(self, command: Command = FASTER, error: Exception | None = None):
        self.command = command
        self.error = error
        self.calls = []

    def __call__(self, text, settings, personality=None):
        self.calls.append((text, settings))
        if self.error:
            raise self.error
        return self.command


class FakeEars:
    """Pretends to transcribe: returns the prepared words."""

    def __init__(self, words: str = "make it faster", error: Exception | None = None):
        self.words = words
        self.error = error
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        return self.words


def fake_voice(_text, _voice_id=None):
    yield b"ID3-first-chunk"
    yield b"-rest-of-the-mp3"


def fake_services(gemini=None, ears=None, speak=fake_voice) -> Services:
    return Services(Pipeline(gemini or FakeGemini(), ears or FakeEars()), speak, ShortTermStore(keep_at_most=10))


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
