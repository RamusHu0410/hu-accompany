"""The clean notes (in seconds) → the tempo, the key, and the notes in beats on the beat grid.

People hum a little ahead or behind the beat, and drift over a phrase. So the tempo is read from the
gaps between one note's start and the next (each on its own, so drift doesn't add up): the tempo at
which those gaps are the simplest lengths (beats, halves, eighths; dotted and triplet ones cost
more), leaning toward everyday humming tempos, then fine-tuned on every gap. Notes are placed the
same way, each from the one before.

The first note is beat 0. Starts and ends snap to sixteenths, or to eighth-note triplets where
those fit clearly better; dotted lengths come out of the sixteenth grid on their own.
"""

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .cleanup import Note
from .config import CLEANUP

TEMPO_RANGE = (60.0, 180.0)
PREFERRED_TEMPO = 100.0  # between two tempos that fit as well (double or half), the nearer one wins
MIN_NOTES_FOR_TEMPO = 3  # with fewer notes there's no rhythm to read: PREFERRED_TEMPO is used
PREFERENCE_WEIGHT = 1.0
# (length in beats between two starts, how much it costs a reading): the plainer, the cheaper
GAP_LENGTHS = ((1, 0.0), (2, 0.05), (1 / 2, 0.1), (4, 0.15), (3, 0.2), (3 / 2, 0.25), (1 / 4, 0.4), (3 / 4, 0.35),
               (5 / 2, 0.4), (7 / 2, 0.45), (1 / 3, 0.45), (2 / 3, 0.5), (5 / 4, 0.55), (7 / 4, 0.55))
GAP_SLOP_S = 0.03  # how far off the beat a hummed (and detected) start typically is
SHORTEST_GAP_S = 0.07  # starts closer than this are one wobbly note, not rhythm
DRIFT_FOLLOW = 0.5  # how much of each note's offset from the grid the placement follows (see _start_beats)
CANDIDATE_STEP = 0.015  # tempos tried are 1.5% apart; each then settles on its own
FIT_ROUNDS = 4
MISFIT_CAP = 0.75  # one note far off the grid (misheard, or sung loosely) counts at most this much against a reading
PLAINNESS_WEIGHT = 3.0  # how much a plain rhythm counts, against how closely the notes fit the grid
TRIPLET_FITS = 0.04  # a triplet position is used when the note is this close to it (in beats)...
SIXTEENTH_MISSES = 0.06  # ...and this far from the nearest sixteenth
TRIPLET_CONTINUES = 0.1  # right after a triplet note, a triplet position this close is used (they come in threes)


@dataclass
class BeatNote:
    pitch: int
    start_beats: float
    duration_beats: float
    velocity: int


def detect_tempo(notes: list[Note]) -> float:
    """The tempo (BPM, one decimal) that reads the hum most simply. Several tempos fit any tune
    (quarter notes at 120 are dotted eighths at 90), so the likeliest few are each tried for real:
    the notes are placed on the grid at that tempo, the tempo is fitted to where they landed over the
    whole phrase (so one note sung early or late barely moves it), and the reading whose notes sit
    closest to the beat, in the plainest rhythm, at an everyday tempo wins."""
    gaps = _gaps(notes)
    if len(notes) < MIN_NOTES_FOR_TEMPO or len(gaps) < 2:
        return PREFERRED_TEMPO
    best = None
    for tempo in _candidates():
        for _ in range(FIT_ROUNDS):  # settle: place the notes, fit the tempo to them, again
            tuned = _fitted(notes, tempo)
            if abs(tuned / tempo - 1) < 0.002:
                break
            tempo = tuned
        score = _reading_cost(notes, tempo) + _preference(tempo)
        if best is None or score < best[0]:
            best = (score, tempo)
    return round(best[1], 1)


def _candidates() -> list[float]:
    """Tempos to try, CANDIDATE_STEP apart (as a ratio) over the whole range."""
    tempos, tempo = [], TEMPO_RANGE[0]
    while tempo <= TEMPO_RANGE[1]:
        tempos.append(tempo)
        tempo *= 1 + CANDIDATE_STEP
    return tempos


def _preference(tempo: float) -> float:
    return PREFERENCE_WEIGHT * math.log2(tempo / PREFERRED_TEMPO) ** 2


def _gaps(notes: list[Note]) -> np.ndarray:
    starts = np.array([n.start for n in notes])
    gaps = np.diff(starts)
    return gaps[gaps >= SHORTEST_GAP_S]


def _fitted(notes: list[Note], tempo: float) -> float:
    """The tempo that best fits where the notes land on the grid at `tempo`: a straight line through
    (beat, time) over the whole phrase, whose slope is the length of a beat."""
    beats = np.array(_start_beats(notes, tempo))
    times = np.array([n.start for n in notes])
    if np.ptp(beats) <= 0:
        return tempo
    seconds_per_beat = float(np.polyfit(beats, times, 1)[0])
    tuned = 60 / seconds_per_beat if seconds_per_beat > 0 else tempo
    return float(min(TEMPO_RANGE[1], max(TEMPO_RANGE[0], tuned)))


_LENGTH_COST = {round(length, 6): cost for length, cost in GAP_LENGTHS}


def _reading_cost(notes: list[Note], tempo: float) -> float:
    """How good a reading at `tempo` is: how far the notes sit from the grid positions they're given
    (in units of typical humming slop), plus how plain the rhythm they make is."""
    beats = np.array(_start_beats(notes, tempo))
    times = np.array([n.start for n in notes])
    slope, intercept = np.polyfit(beats, times, 1) if np.ptp(beats) > 0 else (60 / tempo, times[0])
    misfit = float(np.mean(np.minimum(((times - (slope * beats + intercept)) / GAP_SLOP_S) ** 2, MISFIT_CAP)))
    lengths = np.round(np.diff(beats), 6)
    plainness = float(np.mean([_LENGTH_COST.get(length, 0.6) for length in lengths])) if len(lengths) else 0.0
    return misfit + PLAINNESS_WEIGHT * plainness


def _start_beats(notes: list[Note], tempo: float) -> list[float]:
    """Each note's start on the grid, from the first note. A running correction follows slow drift
    (the singer easing off or pushing on), so it doesn't add up over a phrase, while a single note
    sung early or late only nudges it."""
    beats_per_second = tempo / 60
    first = notes[0].start
    starts: list[float] = []
    correction = 0.0
    for note in notes:
        heard = (note.start - first) * beats_per_second + correction
        if not starts:
            start = 0.0
        else:
            in_triplet = _step(starts[-1]) == 1 / 3
            start = snap(heard, in_triplet)
            if start <= starts[-1]:
                start = starts[-1] + _step(starts[-1])
        correction += DRIFT_FOLLOW * (start - heard)
        starts.append(start)
    return starts



def quantize(notes: list[Note], tempo: float) -> list[BeatNote]:
    """The notes in beats from the first note, snapped to the grid, one at a time and never
    overlapping (see _start_beats for how drift is followed)."""
    beats_per_second = tempo / 60
    out: list[BeatNote] = []
    for note, start in zip(notes, _start_beats(notes, tempo)):
        end = snap(start + (note.end - note.start) * beats_per_second, _step(start) == 1 / 3)
        end = max(end, start + _step(start))
        out.append(BeatNote(note.pitch, start, end - start, note.velocity))
    for current, following in zip(out, out[1:]):  # a note ends where the next begins, at the latest
        current.duration_beats = min(current.duration_beats, following.start_beats - current.start_beats)
    out = _without_slivers(out, CLEANUP.min_note_ms / 1000 * tempo / 60)
    for note in out:
        note.start_beats, note.duration_beats = round(note.start_beats, 6), round(note.duration_beats, 6)
    return out


def _without_slivers(notes: list[BeatNote], shortest: float) -> list[BeatNote]:
    """Snapping two neighbours to different grids (a triplet, then a sixteenth) can squeeze a note
    below the shortest allowed; it joins the note before it (or, if it's first, the one after)."""
    kept: list[BeatNote] = []
    for note in notes:
        if note.duration_beats >= shortest - 1e-9:
            kept.append(note)
        elif kept:
            kept[-1].duration_beats = note.start_beats + note.duration_beats - kept[-1].start_beats
        elif len(notes) > 1:
            notes[1].duration_beats += notes[1].start_beats - note.start_beats
            notes[1].start_beats = note.start_beats
    return kept


def snap(beats: float, in_triplet: bool = False) -> float:
    """The nearest sixteenth, or triplet eighth where that clearly fits (or a triplet is under way)."""
    sixteenth = round(beats * 4) / 4
    triplet = round(beats * 3) / 3
    clearly = abs(beats - triplet) < TRIPLET_FITS and abs(beats - sixteenth) > SIXTEENTH_MISSES
    if clearly or (in_triplet and abs(beats - triplet) < TRIPLET_CONTINUES):
        return triplet
    return sixteenth


def detect_key(notes: list[BeatNote]) -> str:
    """The key, named the music21 way: "D minor", "B- major" (music21 writes flats as -)."""
    from music21 import note as m21_note, stream

    melody = stream.Stream()
    for n in notes:
        melody.append(m21_note.Note(n.pitch, quarterLength=Fraction(n.duration_beats).limit_denominator(12)))  # triplets exactly
    key = melody.analyze("key")
    return f"{key.tonic.name} {key.mode}"


def _step(beat: float) -> float:
    """The grid step at this position: a triplet eighth on a triplet, else a sixteenth."""
    return 1 / 3 if abs(beat * 4 - round(beat * 4)) > 1e-6 else 0.25
