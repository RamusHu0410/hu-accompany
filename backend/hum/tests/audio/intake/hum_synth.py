"""Hums with a known right answer, for the intake tests.

A voice-like tone (a fundamental and fading harmonics, a little breath noise) that sings given notes
the way people hum them: scooping up into some, vibrato on long ones, a slow drift, legato steps
with no gap, same-pitch repeats with a short dip in loudness, all a few cents off true pitch.

HUM_SAMPLE is tests/fixtures/hum_sample.wav's melody. Rebuild the fixture with:
    uv run python -m tests.audio.intake.hum_synth      (from backend/src)
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 44100
HARMONICS = (1.0, 0.45, 0.28, 0.18, 0.11, 0.07, 0.04)
GLIDE_S = 0.035  # a legato step slides this fast
GAP_S = 0.06  # an articulated note stops this much before the next
DIP_S = 0.07  # a repeated note's re-attack: the loudness dips for this long
SCOOP_S = 0.07
SCOOP_SEMITONES = 1.3
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "hum_sample.wav"


@dataclass(frozen=True)
class Sung:
    pitch: int  # MIDI note number
    start: float  # beats
    beats: float
    join: str = "gap"  # how it follows the note before: "gap", "legato" (no pause) or "dip" (re-attack)
    scoop: bool = False
    vibrato: bool = False


HUM_SAMPLE_TEMPO = 92.0
HUM_SAMPLE_TUNING_CENTS = 14
T = 1 / 3
HUM_SAMPLE = [
    Sung(50, 0, 1, scoop=True),  # D3
    Sung(52, 1, 1, "legato"),  # E3, straight on from D3
    Sung(53, 2, 2, "legato", vibrato=True),  # F3, held
    Sung(52, 4, T),  # a triplet: E F E
    Sung(53, 4 + T, T, "legato"),
    Sung(52, 4 + 2 * T, T, "legato"),
    Sung(50, 5, 1, scoop=True),  # D3
    Sung(50, 6, 1, "dip"),  # D3 again, re-attacked
    Sung(52, 7, 1.5, scoop=True),  # E3, dotted
    Sung(50, 8.5, 0.5, "legato"),  # D3
    Sung(50, 9, 2, "dip", vibrato=True),  # D3 again, held
]


def hum(notes: list[Sung], tempo: float = HUM_SAMPLE_TEMPO, tuning_cents: float = HUM_SAMPLE_TUNING_CENTS,
        rate: int = RATE, lead_in: float = 0.45, tail: float = 0.5, vibrato_semitones: float = 0.4, seed: int = 7) -> np.ndarray:
    """The notes hummed, as mono float samples."""
    beat = 60 / tempo
    total = int(rate * (lead_in + max(n.start + n.beats for n in notes) * beat + tail))
    t = np.arange(total) / rate
    pitch = np.full(total, float(notes[0].pitch))
    level = np.zeros(total)
    for i, note in enumerate(notes):
        start, end = lead_in + note.start * beat, lead_in + (note.start + note.beats) * beat
        following = notes[i + 1] if i + 1 < len(notes) else None
        if following is None or following.join == "gap":
            end -= GAP_S
        span = (t >= start) & (t < end)
        here = t[span] - start
        curve = np.full(len(here), float(note.pitch))
        if note.scoop:
            curve -= SCOOP_SEMITONES * np.clip(1 - here / SCOOP_S, 0, 1) ** 2
        if note.vibrato:
            depth = vibrato_semitones * np.clip((here - 0.25) / 0.15, 0, 1)
            curve += depth * np.sin(2 * np.pi * 5.5 * here)
        if note.join == "legato" and i > 0:  # slide over from the note before
            curve += (notes[i - 1].pitch - note.pitch) * np.clip(1 - here / GLIDE_S, 0, 1)
        pitch[span] = curve
        envelope = np.ones(len(here))
        if note.join != "legato":
            envelope *= np.clip(here / 0.025, 0, 1)  # attack
        if following is None or following.join == "gap":
            envelope *= np.clip((end - start - here) / 0.03, 0, 1)  # release
        level[span] = 0.7 * envelope
    for note in notes:  # re-attacks: a short dip in loudness where the repeat begins
        if note.join == "dip":
            at = lead_in + note.start * beat
            dip = np.abs(t - at) < DIP_S / 2
            level[dip] *= 0.08
    rng = np.random.default_rng(seed)
    pitch += tuning_cents / 100 + 0.08 * np.sin(2 * np.pi * 0.7 * t + rng.uniform(0, 6))  # tuning, and a slow drift
    phase = 2 * np.pi * np.cumsum(440 * 2 ** ((pitch - 69) / 12)) / rate
    voice = sum(a * np.sin((k + 1) * phase) for k, a in enumerate(HARMONICS)) / sum(HARMONICS)
    return (level * voice + 0.002 * rng.standard_normal(total)).astype(np.float32)


def write(path, samples: np.ndarray, rate: int = RATE) -> Path:
    sf.write(str(path), samples, rate, subtype="PCM_16")
    return Path(path)


if __name__ == "__main__":
    write(FIXTURE, hum(HUM_SAMPLE))
    print("wrote", FIXTURE)
