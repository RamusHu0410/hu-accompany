"""Tempo and rhythm from hums sung the way people sing: each note up to 25 ms early or late, slow
glides between pitches, scoops, background noise. The tempo used to be read from how well note
starts fit a grid from the first note, which a finer (faster) grid always wins with human timing:
most of these came out at 1.2 to 1.8 times the tempo, with their notes on the wrong beats."""

import random

import numpy as np
import pytest

from hum.engine.audio.intake import transcribe_to_melody

from . import hum_synth
from .hum_synth import HUM_SAMPLE, Sung, hum, write


def _line(pitches, beats, join="gap"):
    out, at = [], 0.0
    for i, pitch in enumerate(pitches):
        out.append(Sung(pitch, at, beats[i % len(beats)], join if i else "gap"))
        at += beats[i % len(beats)]
    return out


TUNES = {
    "hum_sample": (HUM_SAMPLE, 92.0),
    "quarters": (_line([60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60], [1, 1, 1, 1, 1, 1, 2]), 110.0),
    "eighth run": (_line([57, 59, 60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 59, 57], [0.5] * 14 + [2]), 120.0),
    "fast repeated eighths": (_line([64, 64, 64, 62, 60, 60, 60, 62, 64, 64, 64, 64, 62], [0.5] * 12 + [2]), 140.0),
    "legato eighths": (_line([60, 62, 64, 65, 67, 65, 64, 62, 60, 64, 67, 72], [0.5] * 11 + [2], "legato"), 132.0),
}


def _humanized(notes, tempo, seed, jitter_s=0.025):
    rng = random.Random(seed)
    beat = 60 / tempo
    starts = [n.start + (rng.uniform(-jitter_s, jitter_s) / beat if i else 0) for i, n in enumerate(notes)]
    return [Sung(n.pitch, starts[i], max(0.05, (starts[i + 1] if i + 1 < len(notes) else n.start + n.beats) - starts[i]),
                 n.join, scoop=n.scoop or i % 3 == 0, vibrato=n.vibrato) for i, n in enumerate(notes)]


@pytest.mark.parametrize("name", sorted(TUNES))
def test_a_humanly_sung_tune_gets_its_tempo_and_beats(name, tmp_path, monkeypatch):
    monkeypatch.setattr(hum_synth, "GLIDE_S", 0.075)
    monkeypatch.setattr(hum_synth, "SCOOP_S", 0.1)
    monkeypatch.setattr(hum_synth, "DIP_S", 0.05)
    notes, tempo = TUNES[name]
    samples = hum(_humanized(notes, tempo, seed=len(name) + 11), tempo=tempo, tuning_cents=12)
    samples = samples + 0.012 * np.random.default_rng(1).standard_normal(len(samples)).astype(np.float32)
    result = transcribe_to_melody(str(write(tmp_path / "hum.wav", samples)), str(tmp_path / "run"))

    import json

    melody = json.loads(open(result.json_path).read())
    assert melody["tempo_bpm"] == pytest.approx(tempo, rel=0.06)
    heard = [n["start_beats"] for n in melody["notes"]]
    sung = [n.start for n in notes]
    on_the_beat = sum(1 for got, want in zip(heard, sung) if abs(got - want) < 0.13)
    assert len(heard) >= len(sung) - 1 and on_the_beat >= 0.75 * len(sung), (heard, sung)
