"""A tour of the whole pipeline, to see that the parts work together:

    python -m hum.engine.audio.arrange.demo                  # a synthetic hum of the fixture
    python -m hum.engine.audio.arrange.demo --input my.wav   # your own recording
    python -m hum.engine.audio.arrange.demo --stems          # also render each track alone

  1. The fixture melody through the full pipeline (fixture intake), cinematic.
  2. A hum (yours, or one synthesized from the fixture) -> intake (app/audio/intake) ->
     melody.json -> arrangement, with what was sung next to what intake heard.
  3. Run 1's saved melody re-arranged in another style (a re-run from "transform").
  4. Run 1's saved render with only new effects (a re-run from "effects").
  5. A forced effects failure, to show the fallback: final.wav is the plain render.

Every run is a folder under RUNS_DIR (default backend/hum_data/runs); the last lines list what to
listen to.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import logging
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from hum.engine.audio import pipeline
from hum.engine.audio.arrange import debug
from hum.engine.audio.arrange import effects as fx
from hum.engine.audio.arrange.melody import Melody, load_melody


def synthesize_hum(melody: Melody, path: str | Path, sample_rate: int = 22_050, seed: int = 7) -> Path:
    """A believable hum of `melody`: a slightly detuned voice-like tone with vibrato, breath noise,
    soft attacks and a short breath between notes."""
    rng = np.random.default_rng(seed)
    spb = melody.seconds_per_beat
    total = int((melody.end_beats * spb + 0.5) * sample_rate)
    audio = np.zeros(total)
    for n in melody.notes:
        start, length = int(n.start_beats * spb * sample_rate), int((n.duration_beats * spb - 0.06) * sample_rate)
        t = np.arange(length) / sample_rate
        cents = melody.tuning_offset_cents + 18 * np.sin(2 * np.pi * 5.5 * t)
        freq = 440 * 2 ** ((n.pitch - 69 + cents / 100) / 12)
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        voice = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
        envelope = np.minimum(1, np.minimum(t / 0.04, (length / sample_rate - t) / 0.05))
        audio[start:start + length] += 0.25 * (n.velocity / 80) * voice * envelope
    audio += 10 ** (-40 / 20) * rng.standard_normal(total)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio / max(1.0, np.max(np.abs(audio))), sample_rate, subtype="PCM_16")
    return path


@contextlib.contextmanager
def broken_effects():
    """The effects chain raises while this is open (demo only)."""
    real = fx.build_chain

    def fail(_settings):
        raise RuntimeError("simulated effects failure")

    fx.build_chain = fail
    try:
        yield
    finally:
        fx.build_chain = real


def _section(title: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def _compare(sung: Melody, heard: Melody) -> None:
    print("what was sung  vs  what intake heard (per bar):")
    sung_bars, heard_bars = debug.bars_text(sung), debug.bars_text(heard)
    for i in range(max(len(sung_bars), len(heard_bars))):
        left = sung_bars[i].split("| ", 1)[-1] if i < len(sung_bars) else ""
        right = heard_bars[i].split("| ", 1)[-1] if i < len(heard_bars) else ""
        print(f"  bar {i + 1:2d}  {left:44s} | {right}")
    sung_pitches, heard_pitches = [n.pitch for n in sung.notes], [n.pitch for n in heard.notes]
    blocks = difflib.SequenceMatcher(None, sung_pitches, heard_pitches, autojunk=False).get_matching_blocks()
    matched = {i for b in blocks for i in range(b.a, b.a + b.size)}
    missed = [f"{debug.note_name(n.pitch)} (bar {int(n.start_beats // sung.beats_per_bar) + 1}, {n.duration_beats:g} beats)"
              for i, n in enumerate(sung.notes) if i not in matched]
    print(f"  {len(matched)} of {len(sung.notes)} sung notes heard at the right pitch, in order; "
          f"{len(heard.notes) - len(matched)} extra. Missed: {', '.join(missed) or 'none'}")
    print(f"  key {sung.key} vs {heard.key}, tempo {sung.tempo_bpm:g} vs {heard.tempo_bpm:g} BPM, "
          f"tuning {sung.tuning_offset_cents:+g} vs {heard.tuning_offset_cents:+g} cents")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m hum.engine.audio.arrange.demo")
    parser.add_argument("--input", help="a WAV recording to use in scenario 2 (default: a synthetic hum)")
    parser.add_argument("--style", default="cinematic")
    parser.add_argument("--stems", action="store_true", help="render each track of run 1 alone")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)  # keep printed text and log lines in order
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="  %(levelname)s %(message)s")
    from dotenv import load_dotenv

    load_dotenv(pipeline.BACKEND_ROOT / ".env")
    fixture = load_melody(pipeline.FIXTURE_JSON)
    listen: list[tuple[str, str]] = []

    _section(f"1. Fixture melody -> full pipeline ({args.style})")
    first = pipeline.run_pipeline(str(pipeline.FIXTURE_MIDI), args.style, intake="fixture")
    if args.stems:
        debug.render_stems(first.run_dir)
    print(debug.describe(first.run_dir))
    listen.append((f"1. fixture, {args.style}", first.final_wav_path))

    _section("2. A hum -> intake -> arrangement: the whole pipeline")
    if args.input:
        hum = Path(args.input)
    else:
        hum = synthesize_hum(fixture, Path(first.run_dir).parent / "demo_inputs" / f"hum_{first.run_id}.wav")
        print(f"synthesized a hum of the fixture: {hum}")
    second = pipeline.run_pipeline(str(hum), args.style, intake="intake")
    heard = load_melody(Path(second.run_dir) / "melody.json")
    if not args.input:
        _compare(fixture, heard)
    print(debug.describe(second.run_dir))
    listen += [("2. the hum itself", str(hum)), (f"2. the hum arranged, {args.style}", second.final_wav_path)]

    _section("3. Re-run: run 1's melody.json in another style")
    other = "modern" if args.style != "modern" else "classical"
    third = pipeline.rerun(first.run_dir, other, from_step="transform")
    print(debug.describe(third.run_dir))
    listen.append((f"3. fixture, {other} (re-run)", third.final_wav_path))

    _section("4. Re-run: run 1's render with only the piano effects")
    fourth = pipeline.rerun(first.run_dir, "piano", from_step="effects")
    print(debug.describe(fourth.run_dir))
    listen.append(("4. run 1 with piano effects", fourth.final_wav_path))

    _section("5. Fallback: the effects step fails")
    with broken_effects():
        fifth = pipeline.rerun(first.run_dir, args.style, from_step="effects")
    print(debug.describe(fifth.run_dir))
    print(f"fell_back={fifth.fell_back}, warnings={fifth.warnings}")
    listen.append(("5. run 1, no effects (fallback)", fifth.final_wav_path))

    _section("Listen")
    for label, path in listen:
        print(f"  {label:34s} {path}")


if __name__ == "__main__":
    sys.exit(main())
