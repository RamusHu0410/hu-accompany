"""Seeing inside a run: a readable report of every step, and each track rendered on its own.

    python -m hum.engine.audio.pipeline describe <run_dir>
    python -m hum.engine.audio.pipeline stems <run_dir>
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from .config import SAMPLE_RATE, STYLES, find_soundfont
from .files import write_atomically
from .melody import Melody, load_melody
from .orchestrate import find_phrases, harmonize
from .render import synthesize
from .steps import FILES

_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def note_name(pitch: int) -> str:
    return f"{_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _beats(value: float) -> str:
    return f"{value:g}"


def bars_text(melody: Melody, max_bars: int | None = None) -> list[str]:
    """One line per bar: each note as name(length in beats), e.g. "D4(1.5) E4(.5) F4(1)"."""
    bpb, lines = melody.beats_per_bar, []
    for bar in range(melody.bars if max_bars is None else min(melody.bars, max_bars)):
        inside = [n for n in melody.notes if bar * bpb <= n.start_beats < (bar + 1) * bpb]
        lines.append(f"  bar {bar + 1:2d} | " + " ".join(f"{note_name(n.pitch)}({_beats(n.duration_beats)})" for n in inside))
    if max_bars is not None and melody.bars > max_bars:
        lines.append(f"  ... {melody.bars - max_bars} more bars")
    return lines


_QUALITY = {(4, 7): "", (3, 7): "m", (3, 6): "dim", (4, 8): "aug"}


def chord_name(pitch_classes) -> str:
    """(4, 7, 10) -> "Edim"."""
    root, third, fifth = pitch_classes[:3]
    return _NAMES[root] + _QUALITY.get(((third - root) % 12, (fifth - root) % 12), "?")


def _db(value: float) -> str:
    return f"{20 * math.log10(value):6.1f} dBFS" if value > 0 else "   -inf dBFS"


def audio_summary(path: Path) -> str:
    info = sf.info(str(path))
    audio, _ = sf.read(str(path), dtype="float64", always_2d=True)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = math.sqrt(float(np.mean(audio ** 2))) if audio.size else 0.0
    finite = bool(np.all(np.isfinite(audio)))
    return (f"{info.duration:6.2f} s  {info.samplerate} Hz  {info.channels} ch  {info.subtype:7s}"
            f"  peak {_db(peak)}  rms {_db(rms)}  {'ok' if finite else 'NaN/Inf!'}")


def describe(run_dir: str | Path) -> str:
    """A report of a run folder, from whatever files it has."""
    run = Path(run_dir)
    out = [f"Run {run.name}  ({run})"]

    log_path = run / "run.json"
    if log_path.is_file():
        log = json.loads(log_path.read_text())
        out.append(f"status {log.get('status')}  style {log.get('style')}  ensemble {log.get('ensemble') or '-'}"
                   f"  from step {log.get('start_step')}"
                   f"  intake {log.get('intake', '-')}  parent {Path(log['parent_run']).name if log.get('parent_run') else '-'}")
        out.append("steps:")
        for step in log.get("steps", []):
            flags = " FELL BACK" if step.get("fell_back") else ""
            out.append(f"  {step['step']:12s} {step['status']:6s} {step.get('seconds') or 0:6.2f} s  "
                       f"-> {', '.join(step.get('outputs', {}).values()) or '-'}{flags}")
            for warning in step.get("warnings", []):
                out.append(f"      ! {warning}")
            if step.get("error"):
                out.append(f"      X {step['error']}")

    if (run / FILES["melody"]).is_file():
        melody = load_melody(run / FILES["melody"])
        low, high = min(n.pitch for n in melody.notes), max(n.pitch for n in melody.notes)
        out.append(f"\nmelody.json: {len(melody.notes)} notes, {melody.bars} bars, {melody.key}, "
                   f"{melody.tempo_bpm:g} BPM, {melody.time_signature}, range {note_name(low)}-{note_name(high)}, "
                   f"tuning {melody.tuning_offset_cents:+g} cents")
        out += bars_text(melody, max_bars=8)

    if (run / FILES["transform"]).is_file():
        transformed = load_melody(run / FILES["transform"])
        log = json.loads(log_path.read_text()) if log_path.is_file() else {}
        if log and "transform" not in {s["step"] for s in log.get("steps", [])}:
            origin = "copied from the parent run"
        else:
            style = log.get("style")
            origin = f"operations: {STYLES[style].transforms or 'none'}" if style in STYLES else "operations: ?"
        sections = ", ".join(str(s + 1) for s in transformed.sections) or "1"
        out.append(f"\nmelody_transformed.json: {len(transformed.notes)} notes, {transformed.bars} bars, "
                   f"sections start at bar {sections} ({origin})")
        out += bars_text(transformed, max_bars=16)
        out.append("phrases (bars, peak):  " + "   ".join(
            f"{p.start_bar + 1}-{p.end_bar} peak {p.peak_bar + 1}" for p in find_phrases(transformed)))
        chords, warnings = harmonize(transformed)
        out.append("harmony (beat:chord): " + " | ".join(f"{_beats(c.start_beats)}:{chord_name(c.pitch_classes)}" for c in chords))
        out += [f"  ! {w}" for w in warnings]

    if (run / FILES["orchestrate"]).is_file():
        midi = pretty_midi.PrettyMIDI(str(run / FILES["orchestrate"]))
        out.append(f"\narrangement.mid: {len(midi.instruments)} tracks, {midi.get_end_time():.1f} s")
        for inst in midi.instruments:
            instrument = "drum kit" if inst.is_drum else pretty_midi.program_to_instrument_name(inst.program)
            pitches = [n.pitch for n in inst.notes] or [0]
            velocities = [n.velocity for n in inst.notes] or [0]
            out.append(f"  {inst.name:12s} {instrument:24s} {len(inst.notes):4d} notes  "
                       f"pitch {min(pitches)}-{max(pitches)}  velocity {min(velocities)}-{max(velocities)}")

    for key in ("render", "effects"):
        if (run / FILES[key]).is_file():
            out.append(f"{FILES[key]:16s} {audio_summary(run / FILES[key])}")
    stems = sorted((run / "debug").glob("stem_*.wav")) if (run / "debug").is_dir() else []
    for stem in stems:
        out.append(f"  {stem.name:22s} {audio_summary(stem)}")
    return "\n".join(out)


def render_stems(run_dir: str | Path, soundfont: str | Path | None = None) -> list[Path]:
    """Each arrangement track rendered alone, as run_dir/debug/stem_<track>.wav (unnormalized, so
    their levels compare). Stems that already exist are left as they are."""
    run = Path(run_dir)
    midi = pretty_midi.PrettyMIDI(str(run / FILES["orchestrate"]))
    soundfont = soundfont or find_soundfont()
    written = []
    for index, inst in enumerate(midi.instruments):
        target = run / "debug" / f"stem_{inst.name}.wav"
        if target.exists():
            written.append(target)
            continue
        solo = copy.deepcopy(midi)
        solo.instruments = [solo.instruments[index]]
        solo_midi = run / "debug" / f".solo_{inst.name}.mid"
        solo_midi.parent.mkdir(exist_ok=True)
        solo.write(str(solo_midi))
        try:
            audio = synthesize(solo_midi, soundfont)
        finally:
            solo_midi.unlink(missing_ok=True)
        written.append(write_atomically(target, lambda tmp, a=audio: sf.write(str(tmp), a, SAMPLE_RATE, subtype="FLOAT")))
    return written
