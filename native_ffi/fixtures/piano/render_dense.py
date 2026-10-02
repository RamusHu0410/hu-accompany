#!/usr/bin/env python3
"""Render the densest passages of a composer's MAESTRO performances, pedal-free.

Stress test for many voices and thick chords: real performance MIDI
(Rachmaninoff by default: wide voicings, octave doublings, fast passagework),
with the sustain pedal removed so every note ends at its key release, rendered
with the same sampled grand as make_rendered.py. The JSON times are the audio
times exactly.

For each performance, every WINDOW_S window (1 s steps) is scored by how many
keys are down, on average, at the moments notes start; the densest window per
title is kept, then the top --clips overall. Only notes that start inside the
window are rendered, so nothing unscored ever sounds.

usage: python3 fixtures/piano/render_dense.py [--composer NAME] [--clips N] [--out DIR]
  REAL_AUDIO_DIR=fixtures/piano/dense cargo test --release --test real_audio -- --ignored --nocapture

Needs the MAESTRO MIDI cache (python3 fixtures/real/fetch_maestro.py downloads it)
and fluidsynth + the soundfont (python3 fixtures/piano/make_rendered.py fetches it).
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "real"))  # fetch_maestro (+ fetch_guitarset it imports)

from fetch_maestro import CACHE, MIDI_ZIP, METADATA, fetch, parse_midi  # noqa: E402
from make_rendered import LEAD_IN_MS, ensure_soundfont, piece_json, render, validate, write_midi  # noqa: E402

OUT_DIR = HERE / "dense"
WINDOW_S = 20.0
MIN_NOTES = 120
GRID_S = 0.01  # polyphony is sampled every 10 ms


def keys_down(notes, duration_s):
    """Number of keys held at every GRID_S step."""
    n = int(duration_s / GRID_S) + 2
    delta = np.zeros(n + 1)
    for _, on, off, _ in notes:
        delta[int(on / GRID_S)] += 1
        delta[max(int(off / GRID_S), int(on / GRID_S) + 1)] -= 1
    return np.cumsum(delta)[:n]


def densest_window(notes):
    """(score, t0) of the WINDOW_S window with the most keys down at onsets."""
    if len(notes) < MIN_NOTES:
        return None
    onsets = np.array([on for _, on, _, _ in notes])
    down = keys_down(notes, max(off for _, _, off, _ in notes))
    at_onset = down[(onsets / GRID_S).astype(int)]
    best = None
    for t0 in np.arange(0.0, onsets[-1] - WINDOW_S, 1.0):
        inside = (onsets >= t0) & (onsets < t0 + WINDOW_S)
        if inside.sum() < MIN_NOTES:
            continue
        score = at_onset[inside].mean()
        if best is None or score > best[0]:
            best = (score, float(t0))
    return best


def short_title(title):
    keep = "".join(c if c.isalnum() else "_" for c in title)
    return "_".join(p for p in keep.split("_") if p)[:32]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--composer", default="Rachmaninoff")
    parser.add_argument("--clips", type=int, default=4)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    meta = json.loads(fetch(METADATA, CACHE / "maestro-v3.0.0.json").read_text())
    rows = [
        {k: meta[k][i] for k in ("canonical_composer", "canonical_title", "midi_filename")}
        for i in meta["midi_filename"]
        if args.composer.lower() in meta["canonical_composer"][i].lower()
    ]
    midi_zip = zipfile.ZipFile(fetch(MIDI_ZIP, CACHE / "maestro-v3.0.0-midi.zip"))
    names = {Path(n).name: n for n in midi_zip.namelist()}
    print(f"scoring {len(rows)} {args.composer} performances for density...")

    best_per_title = {}
    for r in rows:
        notes, _pedal = parse_midi(midi_zip.read(names[Path(r["midi_filename"]).name]))  # pedal dropped
        w = densest_window(notes)
        if not w:
            continue
        key = r["canonical_title"].lower().replace(" ", "")[:20]  # same piece, different spellings
        if key not in best_per_title or w[0] > best_per_title[key][0]:
            best_per_title[key] = (w[0], w[1], r, notes)

    picks = sorted(best_per_title.values(), key=lambda p: -p[0])[: args.clips]
    soundfont = ensure_soundfont()
    args.out.mkdir(parents=True, exist_ok=True)
    credits = []
    for n, (score, t0, r, notes) in enumerate(picks):
        name = f"{n:02d}_{short_title(r['canonical_title'])}_comp"
        window = [(p, on, off, v) for p, on, off, v in notes if t0 <= on < t0 + WINDOW_S]
        # Whole ms from the window start (+ lead-in), as in make_rendered.py.
        ms = [(p, round((on - t0) * 1000) + LEAD_IN_MS, round((off - t0) * 1000) + LEAD_IN_MS, v) for p, on, off, v in window]
        ms = [(p, s, max(e, s + 1), v) for p, s, e, v in ms]
        validate(name, ms)
        mid, wav, js = (args.out / f"{name}{ext}" for ext in (".mid", ".wav", ".json"))
        write_midi(ms, mid)
        render(mid, wav, soundfont)
        js.write_text(json.dumps(piece_json(name, ms), indent=1))
        poly = keys_down([(p, s / 1000, e / 1000, v) for p, s, e, v in ms], max(e for _, _, e, _ in ms) / 1000)
        low = sum(p < 34 for p, *_ in ms)
        print(f"  {name:<40} {len(ms):>4} notes  keys down at onsets {score:4.1f} (max {int(poly.max())})  below A#1: {low}")
        credits.append(f"{name}: {r['canonical_composer']} - {r['canonical_title']} ({r['midi_filename']}, {t0:.0f}-{t0 + WINDOW_S:.0f} s, pedal removed)")

    (args.out / "ATTRIBUTION.txt").write_text(
        "MIDI from MAESTRO v3.0.0 (Hawthorne et al., ICLR 2019, CC BY-NC-SA 4.0), sustain pedal removed;\n"
        "rendered with YDP-GrandPiano (FreePats, CC BY 3.0).\n\n" + "\n".join(credits) + "\n"
    )
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
