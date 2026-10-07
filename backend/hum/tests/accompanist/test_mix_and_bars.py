"""Tests for melody prominence and chord bar-boundary clamping."""

import pretty_midi

from hum.engine.accompanist.generate import generate_accompaniment


def _eight_bar():
    bar_notes = {
        0: [60, 64, 67, 72], 1: [65, 69, 72, 69], 2: [67, 71, 74, 67],
        3: [72, 67, 64, 60], 4: [69, 72, 76, 69], 5: [65, 69, 72, 65],
        6: [67, 71, 74, 71], 7: [60, 64, 67, 60],
    }
    notes = []
    for bar, ps in bar_notes.items():
        for beat, p in enumerate(ps):
            notes.append({"hz": p, "start": bar * 4 + beat, "duration": 1.0})
    return {"melody": notes, "tempo": 120}


def _bar_seconds(tempo=120, beats_per_bar=4):
    return (60.0 / tempo) * beats_per_bar


def test_melody_louder_than_accompaniment(tmp_path):
    out = tmp_path / "m.mid"
    generate_accompaniment(_eight_bar(), str(out), style="piano")
    pm = pretty_midi.PrettyMIDI(str(out))
    acc, mel = pm.instruments[0], pm.instruments[1]
    assert min(n.velocity for n in mel.notes) > max(n.velocity for n in acc.notes)


def test_no_accompaniment_note_crosses_bar_all_styles(tmp_path):
    bar_s = _bar_seconds()
    for style in ("piano", "pop", "cinematic", "classical", "jazz", "asian_folk"):
        out = tmp_path / f"{style}.mid"
        generate_accompaniment(_eight_bar(), str(out), style=style,
                               key="C", mode="major")
        pm = pretty_midi.PrettyMIDI(str(out))
        acc = pm.instruments[0]
        for n in acc.notes:
            start_bar = int(n.start // bar_s)
            end_bar = int((n.end - 1e-6) // bar_s)
            assert end_bar == start_bar, (
                f"{style}: note {n.pitch} crosses bar boundary "
                f"({n.start:.3f}s -> {n.end:.3f}s)"
            )


def test_jazz_randomness_still_in_bar(tmp_path):
    # Run several times: rubato/random jazz must never cross a bar.
    bar_s = _bar_seconds()
    for r in range(5):
        out = tmp_path / f"jazz{r}.mid"
        generate_accompaniment(_eight_bar(), str(out), style="jazz",
                               key="C", mode="major")
        pm = pretty_midi.PrettyMIDI(str(out))
        for n in pm.instruments[0].notes:
            assert int(n.start // bar_s) == int((n.end - 1e-6) // bar_s)
