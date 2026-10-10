"""Chords for the tune: one per bar, chosen from the key's own chords.

Every chord the key allows is scored, bar by bar, on how well it fits the notes sung over it (long
notes and notes on the strong beats count most). The whole progression is then chosen at once
(dynamic programming over the bars) so it also moves well: strong steps such as V to I are
rewarded, the genre's favourite progressions are leaned toward, the tune starts and ends at home,
and the mood tips close calls toward minor or major chords.
"""

from dataclasses import dataclass

from .presets import Mood, Preset
from .project import BEATS_PER_BAR, ChordSymbol, Note

# Intervals above the root, by chord quality.
QUALITIES = {
    "maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6),
    "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "dom7": (0, 4, 7, 10), "m7b5": (0, 3, 6, 10),
    "power": (0, 7),
}
SEVENTH_OF = {"maj": "maj7", "min": "min7", "dim": "m7b5"}

# (semitones above the tonic, quality, roman numeral) for the chords each mode uses.
DIATONIC = {
    "major": ((0, "maj", "I"), (2, "min", "ii"), (4, "min", "iii"), (5, "maj", "IV"), (7, "maj", "V"), (9, "min", "vi")),
    "minor": ((0, "min", "i"), (3, "maj", "III"), (5, "min", "iv"), (7, "maj", "V"), (7, "min", "v"), (8, "maj", "VI"),
              (10, "maj", "VII")),
}
TONIC = {"major": "I", "minor": "i"}
DOMINANT = "V"
DOMINANT_SEVENTHS = ("V", "VII")  # in minor, VII7 keeps to the key where VIImaj7 would not
SUBDOMINANT = {"major": "IV", "minor": "iv"}

FIT_WEIGHT = 1.5  # the tune comes first: the other terms only settle close calls
STRONG_BEAT = 1.5  # a note on beat 1 or 3 counts this much more
CLASH = 0.9  # how much a note outside the chord counts against it
TEMPLATE_BONUS = 0.12
HOME_BONUS = 0.45  # the first and last bar at home
REPEAT_PENALTY = 0.15
MOOD_BONUS = 0.12
AVOID_PENALTY = 0.6  # enough to change a close call, not to put a chord under notes it clashes with
GOOD_STEPS = {
    ("V", "I"): 0.35, ("V", "i"): 0.35, ("IV", "V"): 0.2, ("iv", "V"): 0.2, ("ii", "V"): 0.25,
    ("vi", "IV"): 0.12, ("IV", "I"): 0.12, ("iv", "i"): 0.12, ("VI", "VII"): 0.15, ("VII", "i"): 0.2,
    ("vi", "ii"): 0.12, ("I", "IV"): 0.08, ("i", "iv"): 0.08, ("iii", "vi"): 0.1, ("VI", "iv"): 0.08,
    ("III", "VII"): 0.08, ("i", "VI"): 0.1, ("VI", "i"): 0.08, ("I", "vi"): 0.08, ("vi", "I"): 0.06,
}


@dataclass(frozen=True)
class Chord:
    root: int  # pitch class
    quality: str
    degree: str

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return tuple((self.root + step) % 12 for step in QUALITIES[self.quality])

    def symbol(self, bar: int) -> ChordSymbol:
        return ChordSymbol(bar, self.root, self.quality, self.degree)

    def name(self) -> str:
        from hum.transcription import NOTE_NAMES

        suffix = {"maj": "", "min": "m", "dim": "dim", "maj7": "maj7", "min7": "m7", "dom7": "7", "m7b5": "m7b5",
                  "power": "5"}[self.quality]
        return NOTE_NAMES[self.root] + suffix


def key_chords(tonic_pc: int, mode: str) -> list[Chord]:
    return [Chord((tonic_pc + step) % 12, quality, degree) for step, quality, degree in DIATONIC[mode]]


def chord_by_degree(tonic_pc: int, mode: str, degree: str) -> Chord:
    return next(c for c in key_chords(tonic_pc, mode) if c.degree == degree)


def progression(melody: list[Note], bars: int, tonic_pc: int, mode: str, preset: Preset, mood: Mood,
                avoid: list[Chord] | None = None) -> list[Chord]:
    """One chord per bar for `bars` bars of `melody` (beats from bar 0), in the plain triad form;
    `colored` adds the genre's sevenths or power chords. `avoid` is a progression to move away from
    (a section played differently): its chord in each bar costs AVOID_PENALTY there, so the result
    changes where the tune allows another chord and keeps the same chord where only it fits."""
    candidates = key_chords(tonic_pc, mode)
    fit = [[_fit(melody, bar, chord) for chord in candidates] for bar in range(bars)]
    if avoid:
        for bar in range(bars):
            fit[bar][candidates.index(avoid[bar])] -= AVOID_PENALTY
    best = None
    for template in preset.progressions.get(mode, ((),)):
        score, chords = _best_path(candidates, fit, template, mode, mood)
        if best is None or score > best[0]:
            best = (score, chords)
    return best[1]


def colored(chord: Chord, preset: Preset) -> Chord:
    if preset.power_chords:
        return Chord(chord.root, "power", chord.degree)
    if not preset.sevenths:
        return chord
    quality = "dom7" if chord.degree in DOMINANT_SEVENTHS else SEVENTH_OF.get(chord.quality, chord.quality)
    return Chord(chord.root, quality, chord.degree)


def _fit(melody: list[Note], bar: int, chord: Chord) -> float:
    """How well the chord sits under the bar's notes, from -CLASH to 1 (0 for an empty bar)."""
    start, end = bar * BEATS_PER_BAR, (bar + 1) * BEATS_PER_BAR
    tones = set(chord.pitch_classes)
    score = total = 0.0
    for note in melody:
        overlap = min(note.end, end) - max(note.start, start)
        if overlap <= 0:
            continue
        weight = overlap * (STRONG_BEAT if _on_strong_beat(max(note.start, start)) else 1.0)
        total += weight
        score += weight if note.pitch % 12 in tones else -CLASH * weight
    return FIT_WEIGHT * score / total if total else 0.0


def _on_strong_beat(beat: float) -> bool:
    return abs(beat % 2) < 1e-6


def _best_path(candidates: list[Chord], fit: list[list[float]], template: tuple, mode: str, mood: Mood):
    bars = len(fit)
    home = TONIC[mode]

    def local(bar: int, chord: Chord) -> float:
        score = fit[bar][candidates.index(chord)]
        if template and chord.degree == template[bar % len(template)]:
            score += TEMPLATE_BONUS
        if bar in (0, bars - 1) and chord.degree == home:
            score += HOME_BONUS
        if mood.chord_lean == "minor" and chord.quality == "min":
            score += MOOD_BONUS
        if mood.chord_lean == "major" and chord.quality == "maj":
            score += MOOD_BONUS
        return score

    def step(before: Chord, after: Chord) -> float:
        if before == after:
            return -REPEAT_PENALTY
        return GOOD_STEPS.get((before.degree, after.degree), 0.0)

    # best[i][c]: (score of the best path ending at chord c in bar i, the chord before it)
    best = [{c: (local(0, c), None) for c in candidates}]
    for bar in range(1, bars):
        row = {}
        for chord in candidates:
            here = local(bar, chord)
            before, score = max(((p, best[-1][p][0] + step(p, chord)) for p in candidates), key=lambda x: x[1])
            row[chord] = (score + here, before)
        best.append(row)
    last = max(best[-1], key=lambda c: best[-1][c][0])
    score = best[-1][last][0]
    path = [last]
    for bar in range(bars - 1, 0, -1):
        path.append(best[bar][path[-1]][1])
    return score, path[::-1]
