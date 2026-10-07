"""The melody, orchestrated: a multi-track General MIDI arrangement.

Tracks (in this order): melody, melody_double (a second instrument on the tune), strings_pad,
figure (the moving accompaniment: ostinato, arpeggio, strumming...), bass, brass, timpani (in the
styles that have it), percussion, then any instruments a listener added.

The piece is read in phrases of PHRASE_BARS bars. Each phrase peaks at the bar holding its
highest melody note: dynamics build toward that bar and ease off after it, the brass swells into
its downbeat, and the percussion hits it. Hits always land on downbeats.

Harmony: by default a small built-in harmonizer picks one of the key's seven triads for each
half bar (Viterbi over melody fit, common chord moves and a closing cadence). Set
config.HARMONY = "accompanist" to use the accompanist's engine instead (imported, never
modified); it's about 0.3 s per bar and can pick chords outside the key, which are then replaced.
If harmonizing fails, every bar gets the tonic chord and a warning says so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pretty_midi
from music21 import pitch as m21pitch

from . import config
from .config import INSTRUMENT_RANGES, Orchestration
from .melody import Melody, empty_midi, key_pitch_classes, key_tonic_and_mode, parse_key, scale_pitch_classes
from .settings import DEFAULT, ENERGY_STEP, ArrangeSettings, ExtraPart
from .transforms import fit_pitches

logger = logging.getLogger(__name__)

TRACKS = ("melody", "melody_double", "strings_pad", "figure", "bass", "brass", "percussion")  # always there
# Ranges for instruments a listener adds that INSTRUMENT_RANGES doesn't list, by what they play.
_DEFAULT_RANGES = {"lead": (55, 91), "chords": (48, 79), "bass": (28, 55)}
PANS = {"melody": 64, "melody_double": 76, "strings_pad": 46, "figure": 54, "bass": 64, "brass": 84,
        "timpani": 70, "percussion": 64}
PAD_PROGRAMS = range(88, 96)  # General MIDI's pads: slow to speak, so the tune gets doubled from the start


def track_names(orchestration: Orchestration) -> list[str]:
    """The tracks this orchestration writes, in order (before any a listener adds)."""
    names = list(TRACKS)
    if orchestration.timpani:
        names.insert(names.index("percussion"), "timpani")
    return names
_QUALITIES = {"major": (0, 4, 7), "minor": (0, 3, 7), "diminished": (0, 3, 6), "augmented": (0, 4, 8)}


@dataclass(frozen=True)
class Phrase:
    start_bar: int
    end_bar: int  # exclusive
    peak_bar: int


@dataclass(frozen=True)
class ChordSpan:
    start_beats: float
    duration_beats: float
    pitch_classes: tuple[int, ...]  # root first

    @property
    def root(self) -> int:
        return self.pitch_classes[0]


def find_phrases(melody: Melody, phrase_bars: int = config.PHRASE_BARS) -> list[Phrase]:
    """Phrases of `phrase_bars` bars, counted afresh from every section start (so an introduction
    doesn't push the tune's phrases out of line; a phrase before a section start may be shorter).
    Each has its peak: the bar where its highest note starts (the later one on a tie). A phrase with
    no tune in it (an introduction, a break) builds toward whatever comes next, so its peak is the
    bar right after it, where the tune arrives (or its own last bar, at the very end)."""
    bpb, phrases = melody.beats_per_bar, []
    starts = sorted({0, *(s for s in melody.sections if 0 < s < melody.bars)})
    bounds = []
    for section_start, section_end in zip(starts, starts[1:] + [melody.bars]):
        for start in range(section_start, section_end, phrase_bars):
            bounds.append((start, min(start + phrase_bars, section_end)))
    for start, end in bounds:
        inside = [n for n in melody.notes if start <= int(n.start_beats // bpb) < end]
        if inside:
            top = max(n.pitch for n in inside)
            peak = max(int(n.start_beats // bpb) for n in inside if n.pitch == top)
        else:
            peak = end if end < melody.bars else end - 1
        phrases.append(Phrase(start, end, peak))
    return phrases


def harmonize(melody: Melody) -> tuple[list[ChordSpan], list[str]]:
    """The chords under the melody (see config.HARMONY), always in the key."""
    tonic, mode = key_tonic_and_mode(melody.key)
    notes = [{"pitch": n.pitch, "start": n.start_beats, "duration": n.duration_beats} for n in melody.notes]
    try:
        if config.HARMONY == "builtin":
            return builtin_progression(melody), []
        from hum.engine.accompanist.music.progression import generate_progression

        progression = generate_progression(
            notes, key=tonic, mode=mode, beats_per_bar=melody.beats_per_bar, num_bars=melody.bars, chords_per_bar=2
        )
        spans = [
            ChordSpan(float(c.start), float(c.duration), _chord_pitch_classes(c.root, c.quality))
            for c in progression
        ]
        if not spans:
            raise ValueError("empty progression")
        return [_in_key(span, melody) for span in spans], []
    except Exception as exc:  # noqa: BLE001 - any failure there: fall back to a plain tonic
        tonic_pc = parse_key(melody.key).tonic.pitchClass
        triad = _QUALITIES["minor" if mode == "minor" else "major"]
        bpb = melody.beats_per_bar
        spans = [ChordSpan(bar * bpb, bpb, tuple((tonic_pc + i) % 12 for i in triad)) for bar in range(melody.bars)]
        return spans, [f"Harmony fell back to the tonic chord: the accompanist's progression failed ({exc})."]


def diatonic_triads(key_name: str) -> list[tuple[int, int, int]]:
    """The triad on each degree of the key's scale (natural minor for minor keys), root first."""
    scale = scale_pitch_classes(key_name)
    return [(scale[d], scale[(d + 2) % 7], scale[(d + 4) % 7]) for d in range(7)]


# Chord moves (between scale degrees, 0 = tonic) that sound natural, in major and minor alike.
_GOOD_MOVES = {(0, 3), (0, 4), (0, 5), (0, 1), (1, 4), (2, 5), (2, 3), (3, 4), (3, 0), (3, 1),
               (4, 0), (4, 5), (5, 3), (5, 1), (5, 4), (6, 0), (6, 2)}


def builtin_progression(melody: Melody) -> list[ChordSpan]:
    """One of the key's triads per half bar (per bar in odd meters), chosen by Viterbi.

    A chord scores for every beat of melody it contains (a note on the slot's first beat counts
    more) and loses for every beat it clashes with. Natural moves (IV-V, V-I, vi-ii...) get a
    bonus, a mid-bar change is discouraged, the diminished triad is avoided, the piece starts on
    the tonic and closes with a cadence (V or IV, then I).
    """
    triads = diatonic_triads(melody.key)
    minor = parse_key(melody.key).mode == "minor"
    diminished = 1 if minor else 6
    bpb = melody.beats_per_bar
    slot = bpb / 2 if bpb >= 4 and bpb % 2 == 0 else bpb
    per_bar = round(bpb / slot)
    count = melody.bars * per_bar

    score = [[0.0] * 7 for _ in range(count)]
    for i in range(count):
        start, end = i * slot, (i + 1) * slot
        for n in melody.notes:
            overlap = min(end, n.end_beats) - max(start, n.start_beats)
            if overlap <= 0:
                continue
            weight = overlap * (1.3 if abs(n.start_beats - start) < 1e-6 else 1.0)
            for degree, triad in enumerate(triads):
                score[i][degree] += weight if n.pitch % 12 in triad else -0.6 * weight
        score[i][diminished] -= 0.4
    score[0][0] += 0.8
    score[-1][0] += 1.5
    for i in range(max(0, count - 2 * per_bar), count - per_bar):
        for degree in (3, 4):
            score[i][degree] += 0.3

    def move(a: int, b: int, same_bar: bool) -> float:
        if a == b:
            return 0.25 if same_bar else -0.05
        if same_bar:
            return -0.5
        return 0.4 if (a, b) in _GOOD_MOVES else 0.0

    best, back = list(score[0]), []
    for i in range(1, count):
        same_bar = i % per_bar != 0
        row, pointers = [], []
        for b in range(7):
            previous = max(range(7), key=lambda a: best[a] + move(a, b, same_bar))
            row.append(best[previous] + move(previous, b, same_bar) + score[i][b])
            pointers.append(previous)
        best, back = row, back + [pointers]
    path = [max(range(7), key=lambda d: best[d])]
    for pointers in reversed(back):
        path.append(pointers[path[-1]])
    path.reverse()

    spans: list[ChordSpan] = []
    for i, degree in enumerate(path):
        if spans and spans[-1].pitch_classes == triads[degree]:
            last = spans[-1]
            spans[-1] = ChordSpan(last.start_beats, last.duration_beats + slot, last.pitch_classes)
        else:
            spans.append(ChordSpan(i * slot, slot, triads[degree]))
    return spans


def _in_key(span: ChordSpan, melody: Melody) -> ChordSpan:
    """`span` if its chord is in the key, else the key's triad that best fits the melody over it.

    The accompanist's engine can pick a chord from outside the key (an E minor, with B natural, in
    D minor), which clashes with a melody that stays in key.
    """
    allowed = key_pitch_classes(melody.key)
    if set(span.pitch_classes) <= allowed:
        return span
    end = span.start_beats + span.duration_beats
    weight = [0.0] * 12
    for n in melody.notes:
        overlap = min(end, n.end_beats) - max(span.start_beats, n.start_beats)
        if overlap > 0:
            weight[n.pitch % 12] += overlap
    best = max(
        diatonic_triads(melody.key),
        key=lambda triad: (sum(weight[pc] for pc in triad), len(set(triad) & set(span.pitch_classes)), triad[0] == span.root),
    )
    return ChordSpan(span.start_beats, span.duration_beats, best)


def _chord_pitch_classes(root: str, quality: str) -> tuple[int, ...]:
    root_pc = m21pitch.Pitch(root[0] + root[1:].replace("b", "-")).pitchClass
    return tuple((root_pc + i) % 12 for i in _QUALITIES.get(quality, _QUALITIES["major"]))


def _level(bar: int, phrase: Phrase, low: int, high: int) -> float:
    """The phrase's dynamic curve: rising from `low` to `high` at the peak, then easing off."""
    if bar <= phrase.peak_bar:
        rise = (bar - phrase.start_bar) / (phrase.peak_bar - phrase.start_bar) if phrase.peak_bar > phrase.start_bar else 1.0
        return low + (high - low) * rise
    fall = (bar - phrase.peak_bar) / max(1, phrase.end_bar - 1 - phrase.peak_bar)
    return high - (high - low) * 0.45 * fall


def _vel(value: float) -> int:
    return int(min(127, max(1, round(value))))


def _nearest_octave(pc: int, target: int, low: int, high: int) -> int:
    """The pitch of class `pc` closest to `target`, within [low, high]."""
    options = [p for p in range(low, high + 1) if p % 12 == pc]
    return min(options, key=lambda p: abs(p - target))


def _voicings(pcs: tuple[int, ...], low: int, high: int) -> list[tuple[int, ...]]:
    """Close-position voicings (each inversion) of a triad whose notes lie in [low, high]."""
    out = []
    for inversion in range(len(pcs)):
        order = pcs[inversion:] + pcs[:inversion]
        for bottom in range(low, high + 1):
            if bottom % 12 != order[0]:
                continue
            voicing, current = [bottom], bottom
            for pc in order[1:]:
                current += (pc - current) % 12 or 12
                voicing.append(current)
            if voicing[-1] <= high:
                out.append(tuple(voicing))
    return out


def orchestrate(melody: Melody, orchestration: Orchestration,
                settings: ArrangeSettings = DEFAULT) -> tuple[pretty_midi.PrettyMIDI, list[str]]:
    """The arrangement MIDI, and any warnings. `settings` can change the lead instrument, add
    instruments and change the energy of each half; without them it's the style as designed."""
    chords, warnings = harmonize(melody)
    phrases = find_phrases(melody)
    logger.debug("orchestrate: %d bars in %s at %g BPM", melody.bars, melody.key, melody.tempo_bpm)
    for p in phrases:
        logger.debug("  phrase bars %d-%d, peak at bar %d", p.start_bar + 1, p.end_bar, p.peak_bar + 1)
    logger.debug("  chords (beat: pitch classes): %s",
                 ", ".join(f"{c.start_beats:g}: {c.pitch_classes}" for c in chords))
    bpb, spb = melody.beats_per_bar, melody.seconds_per_beat
    low_dyn, high_dyn = orchestration.dynamics

    def phrase_of(bar: int) -> Phrase:
        return next(p for p in phrases if p.start_bar <= bar < p.end_bar)

    def level(beat: float) -> float:
        bar = min(int(beat // bpb), melody.bars - 1)
        return _level(bar, phrase_of(bar), low_dyn, high_dyn)

    def sec(beats: float) -> float:
        return beats * spb

    midi = empty_midi(melody)
    tracks = {
        "melody": pretty_midi.Instrument(orchestration.lead if settings.lead is None else settings.lead, name="melody"),
        "melody_double": pretty_midi.Instrument(orchestration.double, name="melody_double"),
        "strings_pad": pretty_midi.Instrument(orchestration.pad, name="strings_pad"),
        "figure": pretty_midi.Instrument(orchestration.figure, name="figure"),
        "bass": pretty_midi.Instrument(orchestration.bass, name="bass"),
        "brass": pretty_midi.Instrument(orchestration.brass, name="brass"),
        **({"timpani": pretty_midi.Instrument(config.TIMPANI, name="timpani")} if orchestration.timpani else {}),
        "percussion": pretty_midi.Instrument(orchestration.kit, is_drum=True, name="percussion"),
    }

    # Melody: moved into the lead's range as a whole (shape kept), shaped by the phrase curve.
    low, high = INSTRUMENT_RANGES.get(tracks["melody"].program, _DEFAULT_RANGES["lead"])
    lead_pitches = fit_pitches([n.pitch for n in melody.notes], low, high, bias=settings.transpose)
    for n, p in zip(melody.notes, lead_pitches):
        velocity = _vel(level(n.start_beats) * n.velocity / 80)
        tracks["melody"].notes.append(pretty_midi.Note(velocity, p, sec(n.start_beats), sec(n.end_beats)))

    # Doubling: a second instrument joins the tune from the second section (or phrase) on, so the
    # sound grows; from the start when the lead is a pad, which alone would blur the tune.
    low, high = INSTRUMENT_RANGES.get(orchestration.double, _DEFAULT_RANGES["lead"])
    target = [p + 12 * orchestration.double_octave for p in lead_pitches]
    if not all(low <= p <= high for p in target):
        target = fit_pitches(target, low, high, bias=round(sum(target) / len(target) - (low + high) / 2))
    joins = 0.0 if tracks["melody"].program in PAD_PROGRAMS else _second_part_start(melody, phrases)
    doubled = [(n, p) for n, p in zip(melody.notes, target) if n.start_beats >= joins] or list(zip(melody.notes, target))
    for n, p in doubled:
        velocity = _vel(level(n.start_beats) * n.velocity / 80 * 0.85)
        tracks["melody_double"].notes.append(pretty_midi.Note(velocity, p, sec(n.start_beats), sec(n.end_beats)))

    # Strings pad: each chord held, voice-led (the voicing that moves least from the last one).
    low, high = INSTRUMENT_RANGES[orchestration.pad]
    previous = None
    for chord in chords:
        options = _voicings(chord.pitch_classes, max(low, 50), min(high, 76))
        voicing = min(options, key=lambda v: sum(abs(a - b) for a, b in zip(v, previous)) if previous else abs(v[0] - 55))
        previous = voicing
        velocity = _vel(level(chord.start_beats) * 0.8)
        for p in voicing:
            tracks["strings_pad"].notes.append(
                pretty_midi.Note(velocity, p, sec(chord.start_beats), sec(chord.start_beats + chord.duration_beats))
            )

    # Figure: the moving accompaniment, in the style's pattern, on each chord.
    low, high = INSTRUMENT_RANGES.get(orchestration.figure, _DEFAULT_RANGES["chords"])
    for chord in chords:
        for at, length, pitches, accent in _figure(orchestration.figure_pattern, chord, bpb, low, high):
            velocity = _vel(level(at) * 0.9 * accent)
            for p in pitches:
                tracks["figure"].notes.append(pretty_midi.Note(velocity, p, sec(at), sec(at + length)))

    # Bass: the chord root, in the bass's range, near the previous root.
    low, high = INSTRUMENT_RANGES[orchestration.bass]
    step = {"whole": None, "half": bpb / 2, "pulse": 0.5}[orchestration.bass_pattern]
    last_root = (low + high) // 2 - 5
    for chord in chords:
        root = _nearest_octave(chord.root, last_root, low, high)
        last_root = root
        onsets = [chord.start_beats] if step is None else [
            chord.start_beats + i * step for i in range(max(1, int(round(chord.duration_beats / step))))
        ]
        length = chord.duration_beats if step is None else step * 0.9
        for onset in onsets:
            accent = 1.0 if (onset % bpb) == 0 else 0.82
            tracks["bass"].notes.append(pretty_midi.Note(_vel(level(onset) * 0.9 * accent), root, sec(onset), sec(onset + length)))

    # Brass: a swell (expression CC11 rising through the bar) into each peak's downbeat, then an
    # accented chord on it. The last bar is a destination too.
    low, high = INSTRUMENT_RANGES[orchestration.brass]
    targets = sorted({p.peak_bar for p in phrases} | {melody.bars - 1})
    brass = tracks["brass"]
    for target in targets:
        if target < 1:
            continue
        swell_start, arrival = (target - 1) * bpb, target * bpb
        swell_chord = _chord_at(chords, swell_start)
        arrival_chord = _chord_at(chords, arrival)
        swell_voicing = min(_voicings(swell_chord.pitch_classes, low + 4, high - 6), key=lambda v: abs(v[0] - 55))
        arrival_voicing = min(_voicings(arrival_chord.pitch_classes, low + 4, high - 6), key=lambda v: abs(v[0] - 55))
        steps = 16
        for i in range(steps):
            brass.control_changes.append(pretty_midi.ControlChange(11, 30 + (127 - 30) * i // (steps - 1), sec(swell_start + bpb * i / steps)))
        for p in swell_voicing:
            brass.notes.append(pretty_midi.Note(96, p, sec(swell_start), sec(arrival)))
        hold = min(bpb, 2.0) if target < melody.bars - 1 else bpb
        for p in arrival_voicing:
            brass.notes.append(pretty_midi.Note(_vel(high_dyn + 8), p, sec(arrival), sec(arrival + hold)))
    if not brass.notes:
        # Nothing to swell into (a one-bar tune): the brass holds the last chord, rising gently.
        last = (melody.bars - 1) * bpb
        voicing = min(_voicings(_chord_at(chords, last).pitch_classes, low + 4, high - 6), key=lambda v: abs(v[0] - 55))
        for i in range(8):
            brass.control_changes.append(pretty_midi.ControlChange(11, 40 + 60 * i // 7, sec(last + bpb * i / 8)))
        for p in voicing:
            brass.notes.append(pretty_midi.Note(_vel(low_dyn), p, sec(last), sec(last + bpb)))
    brass.control_changes.sort(key=lambda cc: cc.time)

    # Timpani: the chord's root on every phrase's first downbeat, and a roll into each peak.
    if orchestration.timpani:
        timpani = tracks["timpani"]
        low, high = INSTRUMENT_RANGES[config.TIMPANI]

        def drum(beat: float, velocity: float, length: float = 1.0) -> None:
            root = _nearest_octave(_chord_at(chords, beat).root, (low + high) // 2, low, high)
            timpani.notes.append(pretty_midi.Note(_vel(velocity), root, sec(beat), sec(beat + length)))

        for phrase in phrases:
            drum(phrase.start_bar * bpb, _level(phrase.start_bar, phrase, low_dyn, high_dyn))
        for target in targets:
            if target >= 1:
                for i in range(8):  # a roll: 32nd notes through the beat before, growing
                    drum(target * bpb - 1 + i * 0.125, 40 + 8 * i, length=0.12)
            drum(target * bpb, high_dyn + 8, length=2.0 if target == melody.bars - 1 else 1.0)

    # Percussion, on the General MIDI drum channel, in the ensemble's kit and its way of playing.
    drums = tracks["percussion"]
    mode = orchestration.percussion

    def hit(note_number: int, beat: float, velocity: float, length: float = 0.25) -> None:
        drums.notes.append(pretty_midi.Note(_vel(velocity), note_number, sec(beat), sec(beat + length)))

    # Every mode lands a crash on each peak's downbeat; the sparse ones also mark each phrase.
    for target in targets:
        hit(config.CRASH, target * bpb, (high_dyn + 6) * (0.7 if mode == "light" else 1.0), length=1.0)
    if mode in ("hits", "light"):
        drum = config.CONCERT_BASS_DRUM if mode == "hits" else config.KICK
        for phrase in phrases:
            hit(drum, phrase.start_bar * bpb, _level(phrase.start_bar, phrase, low_dyn, high_dyn) * (0.7 if mode == "light" else 1.0))
        for target in targets:
            hit(drum, target * bpb, (high_dyn + 10) * (0.7 if mode == "light" else 1.0))
    build_up = {target - 1 for target in targets if target >= 1}  # the bars leading into a peak

    if mode == "hits":
        # A snare roll crescendo through the beat before each peak.
        for target in targets:
            if target < 1:
                continue
            for i in range(4):
                hit(config.SNARE, target * bpb - 1 + i * 0.25, 45 + 15 * i, length=0.2)
    elif mode == "groove":  # a backbeat under every bar
        for bar in range(melody.bars):
            start = bar * bpb
            for beat in range(int(bpb)):
                hit(config.KICK if beat % 2 == 0 else config.SNARE, start + beat, level(start) * (0.9 if beat % 2 == 0 else 0.8))
            for eighth in range(int(bpb * 2)):
                hit(config.CLOSED_HAT, start + eighth * 0.5, level(start) * 0.55, length=0.1)
    elif mode == "rock":  # kick and snare, eighth-note hats, and a tom fill into each peak
        for bar in range(melody.bars):
            start, strength = bar * bpb, level(bar * bpb)
            fill = bar in build_up
            for beat in range(int(bpb)):
                if fill and beat == int(bpb) - 1:
                    for i, tom in enumerate((config.HIGH_TOM, config.HIGH_TOM, config.MID_TOM, config.LOW_TOM)):
                        hit(tom, start + beat + i * 0.25, strength * (0.8 + 0.07 * i), length=0.2)
                    continue
                hit(config.KICK if beat % 2 == 0 else config.SNARE, start + beat, strength * (0.95 if beat % 2 == 0 else 0.9))
                if beat == 2 and bar % 2 == 1:
                    hit(config.KICK, start + beat + 0.5, strength * 0.75)  # a push on the "and" of three
                for half in (0.0, 0.5):
                    hit(config.CLOSED_HAT, start + beat + half, strength * (0.6 if half == 0 else 0.45), length=0.1)
    elif mode == "electronic":  # four on the floor, claps, off-beat open hats, sixteenth hats
        for bar in range(melody.bars):
            start, strength = bar * bpb, level(bar * bpb)
            for beat in range(int(bpb)):
                hit(config.KICK, start + beat, strength)
                if beat % 2 == 1:
                    hit(config.CLAP, start + beat, strength * 0.85)
                hit(config.OPEN_HAT, start + beat + 0.5, strength * 0.5, length=0.2)
                for sixteenth in (0.25, 0.75):
                    hit(config.CLOSED_HAT, start + beat + sixteenth, strength * 0.35, length=0.1)
            if bar in build_up:  # a snare build: sixteenths getting louder through the bar
                steps = int(bpb * 4)
                for i in range(steps):
                    hit(config.SNARE, start + i * 0.25, 30 + 70 * i / (steps - 1), length=0.15)
    elif mode == "light":  # brushes: a soft backbeat and a ride cymbal on every beat
        for bar in range(melody.bars):
            start, strength = bar * bpb, level(bar * bpb)
            for beat in range(int(bpb)):
                hit(config.RIDE, start + beat, strength * 0.5, length=0.5)
                if beat % 2 == 1:
                    hit(config.SNARE, start + beat, strength * 0.45)

    # Instruments the listener added, each only in its section.
    pans = dict(PANS)
    for index, part in enumerate(settings.parts):
        name = f"extra_{index + 1}_{part.kind}"
        tracks[name] = _extra_part(part, name, chords, melody)
        pans[name] = 40 + (index * 23) % 50

    # Energy: each half a little calmer or bigger, every track alike.
    if settings.energy != (0, 0):
        half = sec(melody.bars * bpb / 2)
        for track in tracks.values():
            for n in track.notes:
                n.velocity = _vel(n.velocity * (1 + ENERGY_STEP * settings.energy[0 if n.start < half else 1]))

    # Mix: volume and pan per track, at the start.
    volumes = dict(orchestration.volumes)
    if settings.lead_volume is not None:
        volumes["melody"] = settings.lead_volume
    volumes.update({f"extra_{i + 1}_{p.kind}": p.volume for i, p in enumerate(settings.parts)})
    for name, track in tracks.items():
        track.control_changes[:0] = [
            pretty_midi.ControlChange(7, volumes.get(name, 90), 0.0),
            pretty_midi.ControlChange(10, pans[name], 0.0),
        ]
        track.notes.sort(key=lambda n: (n.start, n.pitch))
        midi.instruments.append(track)
        pitches = [n.pitch for n in track.notes] or [0]
        logger.debug("  track %-11s program %3d%s: %3d notes, pitch %d-%d", name, track.program,
                     " (drums)" if track.is_drum else "", len(track.notes), min(pitches), max(pitches))
    return midi, warnings


def _second_part_start(melody: Melody, phrases: list[Phrase]) -> float:
    """Where the tune's second part begins, in beats: the second section if the transformations
    made one, else the second phrase, else halfway."""
    bpb = melody.beats_per_bar
    first_note = melody.notes[0].start_beats if melody.notes else 0.0
    # the tune's own sections: not an introduction before its first note
    later_sections = [s for s in melody.sections if s * bpb > first_note + 1e-9]
    if later_sections:
        return later_sections[0] * bpb
    later_phrases = [p for p in phrases if p.start_bar * bpb > first_note + 1e-9]
    if later_phrases:
        return later_phrases[0].start_bar * bpb
    return (first_note + melody.end_beats) / 2


def _figure(pattern: str, chord: ChordSpan, bpb: float, low: int, high: int):
    """The accompaniment figure over one chord: (beat, length, pitches, accent) events, in step with
    the bar (the pattern restarts on every downbeat)."""
    third, fifth = ((pc - chord.root) % 12 for pc in chord.pitch_classes[1:3])
    register = {"ostinato": 0.2, "broken": 0.15, "alberti": 0.3, "arpeggio": 0.35, "comping": 0.4,
                "power": 0.15, "arp16": 0.3}[pattern]
    root = _nearest_octave(chord.root, round(low + (high - low) * register), low, max(low + 11, high - 12))
    r, t, f, o = root, root + third, root + fifth, root + 12
    steps = {
        "ostinato": (0.5, [[r], [f], [o], [f]], 0.4),  # driving strings: root fifth octave fifth
        "alberti": (0.5, [[r], [f], [t + 12 if t + 12 <= high else t], [f]], 0.45),  # low, high, middle, high
        "arpeggio": (0.5, [[r], [t], [f], [o], [f], [t]], 0.5),  # up and down, over and over
        "broken": (1.0, [[r], [f], [t + 12 if t + 12 <= high else t], [f]], 0.95),  # a left hand, in quarters
        "comping": (None, [[t, f, o]], 0.35),  # strummed chords, off the beat
        "power": (0.5, [[r, f, o]], 0.35),  # driving power chords in eighths
        "arp16": (0.25, [[r], [t], [f], [o], [t + 12], [o], [f], [t]], 0.22),  # a fast synth arpeggio, up and down
    }
    step, cells, length = steps[pattern]
    end = chord.start_beats + chord.duration_beats
    events = []
    if pattern == "comping":
        bar_start = (chord.start_beats // bpb) * bpb
        while bar_start < end:
            for offset in (0.0, 0.375 * bpb, 0.5 * bpb, 0.875 * bpb):
                at = bar_start + offset
                if chord.start_beats <= at < end:
                    events.append((at, length, [p for p in cells[0] if low <= p <= high], 1.0 if offset == 0 else 0.8))
            bar_start += bpb
        return events
    at = chord.start_beats
    while at < end - 1e-9:
        index = round((at % bpb) / step)
        pitches = [p for p in cells[index % len(cells)] if low <= p <= high] or [r]
        events.append((at, min(length, end - at), pitches, 1.0 if abs(at % bpb) < 1e-9 else 0.85))
        at += step
    return events


def _extra_part(part: ExtraPart, name: str, chords: list[ChordSpan], melody: Melody) -> pretty_midi.Instrument:
    """A listener's added instrument: held chords, a bass line or a backbeat, only in its section."""
    bpb, spb = melody.beats_per_bar, melody.seconds_per_beat
    total = melody.bars * bpb
    start, end = {"all": (0.0, total), "start": (0.0, total / 2), "end": (total / 2, total)}[part.section]
    if part.kind == "drums":
        track = pretty_midi.Instrument(0, is_drum=True, name=name)
        bar = int(start // bpb)
        while bar * bpb < end:
            for beat in range(int(bpb)):
                at = bar * bpb + beat
                track.notes.append(pretty_midi.Note(80 if beat % 2 == 0 else 72, config.KICK if beat % 2 == 0 else config.SNARE, at * spb, (at + 0.25) * spb))
            for eighth in range(int(bpb * 2)):
                at = bar * bpb + eighth * 0.5
                track.notes.append(pretty_midi.Note(50, config.CLOSED_HAT, at * spb, (at + 0.1) * spb))
            bar += 1
        return track

    track = pretty_midi.Instrument(part.program, name=name)
    low, high = INSTRUMENT_RANGES.get(part.program, _DEFAULT_RANGES[part.kind])
    previous = None
    for chord in chords:
        on, off = max(start, chord.start_beats), min(end, chord.start_beats + chord.duration_beats)
        if off <= on:
            continue
        if part.kind == "bass":
            pitches = (_nearest_octave(chord.root, (low + high) // 2 - 5, low, high),)
        else:
            options = _voicings(chord.pitch_classes, low, high)
            pitches = min(options, key=lambda v: sum(abs(a - b) for a, b in zip(v, previous)) if previous else abs(v[0] - 57))
            previous = pitches
        for p in pitches:
            track.notes.append(pretty_midi.Note(70, p, on * spb, off * spb))
    return track


def _chord_at(chords: list[ChordSpan], beat: float) -> ChordSpan:
    for chord in chords:
        if chord.start_beats <= beat < chord.start_beats + chord.duration_beats:
            return chord
    return chords[-1]

