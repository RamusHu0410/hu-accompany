"""Melody transformations (music21 + arvo), and the style presets that chain them.

Every operation takes a music21 Part and returns a NEW Part; none changes its input. Pitches only
ever move along the key's scale (or by octaves), so a transformed melody stays in key. Sections
that are added (a sequence, an additive build-up, a restatement) start on a bar line, so the
downbeats still line up for the orchestration.

arvo 0.3.0 (the latest release) predates music21 10: its processes read `Stream.flat`, which
music21 10 removed, and its `scalar_transposition` calls a renamed Scale method. So:
  - `additive` uses arvo's `minimalism.additive_process` through `_ArvoStream`, which gives it
    a `.flat` again;
  - diatonic transposition is done here, on the key's scale.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import replace
from typing import Callable

from arvo import minimalism
from music21 import note, stream

from .melody import Melody, Note, from_stream, key_name, key_pitch_classes, parse_key, scale_pitch_classes, to_stream
from .settings import ArrangeSettings

logger = logging.getLogger(__name__)

# A transformed melody longer than this many bars is refused (the orchestration and render
# would take too long, and it's no longer the user's tune).
MAX_BARS = 32


class MelodyTooLong(ValueError):
    """The style's transformations would make the melody longer than MAX_BARS."""


class _ArvoStream(stream.Stream):
    """A Stream arvo 0.3.0 can read: it still calls `.flat`, removed in music21 10."""

    @property
    def flat(self):
        return self.flatten()


# --- helpers ----------------------------------------------------------------------------------


def _notes(part: stream.Stream) -> list[note.GeneralNote]:
    return list(part.flatten().notes)


def _span(part: stream.Stream, bpb: float) -> float:
    """The part's length rounded up to whole bars (at least one)."""
    end = max((float(n.offset) + float(n.quarterLength) for n in _notes(part)), default=0.0)
    return max(1, math.ceil(end / bpb - 1e-9)) * bpb


def _empty_like(part: stream.Stream) -> stream.Part:
    """A new Part with `part`'s tempo, meter and key, and no notes."""
    out = stream.Part()
    for element in part.flatten().getElementsByClass(["MetronomeMark", "TimeSignature", "Key"]):
        out.insert(0, copy.deepcopy(element))
    return out


def _add(out: stream.Part, notes, shift: float = 0.0, pitch: Callable[[int], int] | None = None) -> None:
    """Copies of `notes` into `out`, moved `shift` beats later and repitched by `pitch`."""
    for n in notes:
        clone = copy.deepcopy(n)
        if pitch is not None:
            for p in clone.pitches:
                p.midi = pitch(p.midi)
        out.insert(float(n.offset) + shift, clone)


def _first_bars(part: stream.Stream, bars: int, bpb: float) -> list[note.GeneralNote]:
    """The notes that start within the first `bars` bars, cut off at the last bar line."""
    limit = bars * bpb
    segment = []
    for n in _notes(part):
        if float(n.offset) >= limit:
            continue
        clone = copy.deepcopy(n)
        clone.quarterLength = min(float(n.quarterLength), limit - float(n.offset))
        clone.offset = float(n.offset)
        segment.append(clone)
    return segment


def _last_bars(part: stream.Stream, bars: int, bpb: float) -> list[note.GeneralNote]:
    """The notes of the last `bars` bars, with offsets relative to where that section starts."""
    start = max(0.0, _span(part, bpb) - bars * bpb)
    section = []
    for n in _notes(part):
        if float(n.offset) >= start:
            clone = copy.deepcopy(n)
            clone.offset = float(n.offset) - start
            section.append(clone)
    return section


def scale_ladder(key_name: str) -> list[int]:
    """Every MIDI pitch in the key's scale, low to high."""
    classes = key_pitch_classes(key_name)
    return [p for p in range(128) if p % 12 in classes]


def diatonic_shift(pitch: int, steps: int, key_name: str) -> int:
    """`pitch` moved `steps` scale degrees (7 = an octave in a 7-note scale). A note outside the
    scale keeps its offset from the scale note below it."""
    ladder = scale_ladder(key_name)
    base_index = max(i for i, p in enumerate(ladder) if p <= pitch) if pitch >= ladder[0] else 0
    target = base_index + steps
    if not 0 <= target < len(ladder):
        raise ValueError(f"Moving {pitch} by {steps} steps leaves the MIDI range.")
    return ladder[target] + (pitch - ladder[base_index])


# --- operations: Part -> new Part --------------------------------------------------------------


def repeat(part: stream.Part, *, times: int = 2, bpb: float = 4.0, **_) -> stream.Part:
    """The melody `times` times in a row, each time starting on a bar line."""
    if times < 1:
        raise ValueError("times must be at least 1.")
    span, out = _span(part, bpb), _empty_like(part)
    for i in range(times):
        _add(out, _notes(part), shift=i * span)
    return out


def augment(part: stream.Part, *, factor: float = 2.0, **_) -> stream.Part:
    """Every onset and duration scaled by `factor` (>1 augments, <1 diminishes)."""
    if factor <= 0:
        raise ValueError("factor must be positive.")
    scaled = part.flatten().augmentOrDiminish(factor)
    out = _empty_like(part)
    _add(out, list(scaled.notes))
    return out


def diminish(part: stream.Part, *, factor: float = 2.0, **_) -> stream.Part:
    """Every onset and duration divided by `factor`."""
    return augment(part, factor=1.0 / factor)


def transpose(part: stream.Part, *, steps: int, key: str, **_) -> stream.Part:
    """Every note moved `steps` degrees along the key's scale (stays in key)."""
    out = _empty_like(part)
    _add(out, _notes(part), pitch=lambda p: diatonic_shift(p, steps, key))
    return out


def octave(part: stream.Part, *, octaves: int, **_) -> stream.Part:
    out = _empty_like(part)
    _add(out, _notes(part), pitch=lambda p: p + 12 * octaves)
    return out


def sequence(part: stream.Part, *, key: str, bpb: float = 4.0, bars: int = 1, steps=(1, 2), **_) -> stream.Part:
    """A sequence as an introduction: the opening `bars` bars, then that figure again at each of
    `steps` scale degrees away, then the melody itself."""
    figure = _first_bars(part, bars, bpb)
    length, out = bars * bpb, _empty_like(part)
    _add(out, figure)
    for i, step in enumerate(steps, start=1):
        _add(out, figure, shift=i * length, pitch=lambda p, s=step: diatonic_shift(p, s, key))
    _add(out, _notes(part), shift=(len(steps) + 1) * length)
    return out


def additive(part: stream.Part, *, bpb: float = 4.0, bars: int = 1, **_) -> stream.Part:
    """A minimalist build-up (arvo's additive process) on the opening `bars` bars: 1 note, then 2,
    then 3... then the melody, from the next bar line."""
    source = _ArvoStream()
    for n in _first_bars(part, bars, bpb):
        source.insert(float(n.offset), n)
    built = minimalism.additive_process(source)
    out = _empty_like(part)
    _add(out, list(built.flatten().notes))
    _add(out, _notes(part), shift=_span(built, bpb))
    return out


def restate(part: stream.Part, *, key: str, bpb: float = 4.0, bars: int = 4, steps: int = 7, **_) -> stream.Part:
    """The melody, then its last `bars` bars again `steps` scale degrees higher (7 = an octave):
    a climax to end on."""
    out = _empty_like(part)
    _add(out, _notes(part))
    _add(out, _last_bars(part, bars, bpb), shift=_span(part, bpb), pitch=lambda p: diatonic_shift(p, steps, key))
    return out


OPERATIONS: dict[str, Callable[..., stream.Part]] = {
    "repeat": repeat,
    "augment": augment,
    "diminish": diminish,
    "transpose": transpose,
    "octave": octave,
    "sequence": sequence,
    "additive": additive,
    "restate": restate,
}


# Where each operation puts the sections (the bars where the tune, or an added part, begins).
def _moved_sections(name: str, params: dict, sections: list[int], bars_before: int, bars_after: int) -> list[int]:
    if name == "repeat":
        return [s + copy_ * bars_before for copy_ in range(params.get("times", 2)) for s in sections]
    if name in ("augment", "diminish"):
        factor = params.get("factor", 2.0)
        return [round(s * (factor if name == "augment" else 1 / factor)) for s in sections]
    if name in ("sequence", "additive"):  # an introduction in front of the tune
        return [0] + [s + bars_after - bars_before for s in sections]
    if name == "restate":  # a new section after the tune
        return sections + [bars_before]
    return sections


def apply_operations(melody: Melody, operations: list[tuple[str, dict]], max_bars: int = MAX_BARS) -> Melody:
    """Run `operations` (name, params) in order. Raises ValueError if one is unknown, the result is
    too long, or a pitch left the key or the MIDI range. The result's `sections` say where each part
    of it begins, so the orchestration can phrase it."""
    part = to_stream(melody)
    bpb = melody.beats_per_bar
    context = {"key": melody.key, "bpb": bpb}
    sections = list(melody.sections) or [0]
    for name, params in operations:
        if name not in OPERATIONS:
            raise ValueError(f"Unknown transformation {name!r}.")
        before = round(_span(part, bpb) / bpb)
        part = OPERATIONS[name](part, **{**context, **params})
        sections = _moved_sections(name, params, sections, before, round(_span(part, bpb) / bpb))
        logger.debug("transform %s%s: %d -> %d bars, sections start at bars %s",
                     name, params or "", before, round(_span(part, bpb) / bpb), [s + 1 for s in sections])

    result = from_stream(part, melody)
    result = replace(result, sections=tuple(sorted({s for s in sections if 0 <= s < result.bars})))
    if not result.notes:
        raise ValueError("The transformations left no notes.")
    if result.bars > max_bars:
        raise MelodyTooLong(f"The transformed melody is {result.bars} bars, more than {max_bars}.")
    allowed = key_pitch_classes(melody.key) | {n.pitch % 12 for n in melody.notes}
    strays = sorted({n.pitch for n in result.notes if n.pitch % 12 not in allowed or not 0 <= n.pitch <= 127})
    if strays:
        raise ValueError(f"The transformations left the key: {strays}.")
    return result


def apply_settings(melody: Melody, settings: ArrangeSettings) -> Melody:
    """The melody at the listener's tempo, in their mode (major/minor), moved by their transposition.
    The key name follows, so everything after stays in key."""
    tonic = parse_key(melody.key).tonic.pitchClass
    mode = parse_key(melody.key).mode
    notes = list(melody.notes)

    if settings.mode and settings.mode != mode:
        # each scale degree moves to the same degree of the other mode (in D: F -> F#, Bb -> B, C -> C#)
        source = scale_pitch_classes(melody.key)
        target = scale_pitch_classes(key_name(tonic, settings.mode))
        moves = {s: ((t - s + 6) % 12) - 6 for s, t in zip(source, target)}
        notes = [Note(n.pitch + moves.get(n.pitch % 12, 0), n.start_beats, n.duration_beats, n.velocity) for n in notes]
        mode = settings.mode

    if settings.transpose:
        notes = [Note(_fold(n.pitch + settings.transpose), n.start_beats, n.duration_beats, n.velocity) for n in notes]
        tonic = (tonic + settings.transpose) % 12

    tempo = round(min(300.0, max(20.0, melody.tempo_bpm * settings.tempo_scale)), 1)
    return replace(melody, tempo_bpm=tempo, key=key_name(tonic, mode), notes=tuple(notes))


def _fold(pitch: int) -> int:
    while pitch < 0:
        pitch += 12
    while pitch > 127:
        pitch -= 12
    return pitch


# --- the song's shape around the tune -----------------------------------------------------------


def fill(melody: Melody, bars: int, phrase_bars: int = 4) -> Melody:
    """A tune shorter than `bars` repeated until it's at least that long (a hum is often only a few
    bars; a song needs room to build), each repeat marked as a new section. A tune that's longer,
    but not a whole number of phrases, is rounded up to one with rests."""
    bpb = melody.beats_per_bar
    length = melody.bars
    if length > bars // 2:
        whole = math.ceil(length / phrase_bars) * phrase_bars
        return replace(melody, length_bars=whole) if whole != length else melody
    unit = next(u for u in (1, 2, 4) if u >= length) if length < phrase_bars else length
    copies = min(math.ceil(bars / unit), 8)
    notes = [Note(n.pitch, n.start_beats + k * unit * bpb, n.duration_beats, n.velocity) for k in range(copies) for n in melody.notes]
    sections = sorted({s + k * unit for k in range(copies) for s in (melody.sections or (0,))})
    return replace(melody, notes=tuple(notes), sections=tuple(sections), length_bars=copies * unit)


def frame(melody: Melody, intro_bars: int, outro_bars: int) -> Melody:
    """Room around the tune: `intro_bars` for the band alone before it, building into its first
    note, and `outro_bars` after it for the last chord to ring."""
    if not intro_bars and not outro_bars:
        return melody
    shift = intro_bars * melody.beats_per_bar
    notes = [Note(n.pitch, n.start_beats + shift, n.duration_beats, n.velocity) for n in melody.notes]
    sections = [0] + [s + intro_bars for s in (melody.sections or (0,))]
    length = intro_bars + melody.bars + outro_bars
    if outro_bars:
        sections.append(length - outro_bars)
    return replace(melody, notes=tuple(notes), sections=tuple(sorted(set(sections))), length_bars=length)


def fit_pitches(pitches: list[int], low: int, high: int, bias: int = 0) -> list[int]:
    """Move a line into an instrument's range: the whole line by octaves so its middle sits in the
    range (keeping its shape), then any note still outside folded in by octaves. `bias` (semitones)
    aims the middle higher or lower, so a transposition by an octave is still heard."""
    if not pitches:
        return []
    if high - low < 12:
        raise ValueError("A range must span at least an octave.")
    middle = (min(pitches) + max(pitches)) / 2
    aim = min(high - 6, max(low + 6, (low + high) / 2 + bias))
    shift = 12 * round((aim - middle) / 12)
    fitted = []
    for p in pitches:
        p += shift
        while p < low:
            p += 12
        while p > high:
            p -= 12
        fitted.append(p)
    return fitted
