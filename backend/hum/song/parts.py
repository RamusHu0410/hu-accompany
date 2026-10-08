"""The band's pitched parts, a bar at a time: chords, bass and pad.

Chords and the pad are voiced under a ceiling just below the melody's lowest note, so the tune is
always the highest thing playing. Each chord voicing is the inversion closest to the one before it
(smooth voice leading). The bass plays roots and fifths in the low register.
"""

from .harmony import QUALITIES, Chord
from .project import BEATS_PER_BAR, Note

STEP = BEATS_PER_BAR / 16
CHORD_FLOOR = 48  # C3: lower than this, chords turn to mud
BASS_LOW, BASS_HIGH = 28, 40  # E1 up to (not including) E2 for the root
PAD_LOW = 43
POWER_LOW = 40  # power chords sit where a guitar plays them
STRUM_SPREAD = 0.02  # beats between strings in a strum

# (step, length in steps, how hard) within a bar of 16 sixteenths
COMPING = {
    "hold": ((0, 16, 1.0),),
    "pulse": ((0, 4, 1.0), (4, 4, 0.8), (8, 4, 0.9), (12, 4, 0.8)),
    "lofi": ((0, 6, 1.0), (6, 10, 0.85)),
    "power8": tuple((i * 2, 2, 1.0 if i % 2 == 0 else 0.82) for i in range(8)),
    "power_hold": ((0, 8, 1.0), (8, 8, 0.9)),
    "stab": ((2, 2, 0.95), (6, 2, 0.9), (10, 2, 0.95), (14, 2, 0.9)),
    "charleston": ((0, 3, 1.0), (6, 4, 0.85)),
    "strum": ((0, 4, 1.0), (4, 2, 0.8), (6, 4, 0.85), (10, 2, 0.75), (12, 2, 0.85), (14, 2, 0.75)),
    "arp": (),  # played note by note: see chord_bar
}
UP_STROKES = {(4, 2), (10, 2), (14, 2)}  # in "strum", these hits go from the top string down
BASS_LINES = ("hold", "root_fifth", "eighths", "lofi", "offbeat", "walking")


def voice(chord: Chord, floor: int, ceiling: int, previous: list[int] | None) -> list[int]:
    """The chord's notes between floor and ceiling (inclusive), as the inversion that moves least
    from `previous`, or the one nearest the middle of the range when there is none."""
    if chord.quality == "power":
        root = _in_range(chord.root, POWER_LOW, POWER_LOW + 12)
        return [p for p in (root, root + 7, root + 12) if p <= ceiling] or [root]
    classes = list(chord.pitch_classes)
    options = []
    for turn in range(len(classes)):
        order = classes[turn:] + classes[:turn]
        for low in range(floor, ceiling + 1):
            if low % 12 != order[0]:
                continue
            notes = [low]
            for pc in order[1:]:
                notes.append(notes[-1] + (pc - notes[-1]) % 12)
            if notes[-1] <= ceiling:
                options.append(notes)
    if not options:  # the range is too small for the whole chord: keep what fits, top down
        notes = sorted({_highest_at_most(pc, ceiling) for pc in classes})
        return [n for n in notes if n >= floor - 12] or notes[-1:]
    if previous:
        return min(options, key=lambda v: (_movement(previous, v), -v[-1]))
    middle = (floor + ceiling) / 2
    return min(options, key=lambda v: abs(sum(v) / len(v) - middle))


def chord_bar(voicing: list[int], pattern: str, bar: int, velocity: int) -> list[Note]:
    start = bar * BEATS_PER_BAR
    if pattern == "arp":
        order = voicing + voicing[-2:0:-1] if len(voicing) > 2 else voicing
        return [
            Note(order[i % len(order)], start + i * 2 * STEP, 2 * STEP, _vel(velocity * (1.0 if i % 4 == 0 else 0.85)))
            for i in range(8)
        ]
    notes = []
    for step, length, weight in COMPING[pattern]:
        strings = voicing[::-1] if pattern == "strum" and (step, length) in UP_STROKES else voicing
        for i, pitch in enumerate(strings):
            spread = i * STRUM_SPREAD if pattern == "strum" else 0.0
            notes.append(Note(pitch, start + step * STEP + spread, length * STEP - spread, _vel(velocity * weight)))
    return notes


def bass_bar(chord: Chord, following: Chord | None, line: str, bar: int, velocity: int,
             scale: frozenset[int] = frozenset(range(12))) -> list[Note]:
    """`scale` is the key's pitch classes: a walking line steps into the next chord from inside it."""
    start = bar * BEATS_PER_BAR
    root = _in_range(chord.root, BASS_LOW, BASS_HIGH)
    fifth = root + 7 if root + 7 < BASS_HIGH + 5 else root - 5
    if line == "hold":
        return [Note(root, start, 4.0, _vel(velocity))]
    if line == "root_fifth":
        return [Note(root, start, 2.0, _vel(velocity)), Note(fifth, start + 2, 2.0, _vel(velocity * 0.88))]
    if line == "eighths":
        return [Note(root, start + i * 0.5, 0.5, _vel(velocity * (1.0 if i % 2 == 0 else 0.85))) for i in range(8)]
    if line == "lofi":
        return [Note(root, start, 1.5, _vel(velocity)), Note(root, start + 2.5, 1.5, _vel(velocity * 0.85))]
    if line == "offbeat":
        return [Note(root, start + 0.5 + i, 0.5, _vel(velocity)) for i in range(4)]
    if line == "walking":
        third = root + QUALITIES[chord.quality][1]
        target = _in_range(following.root, BASS_LOW, BASS_HIGH) if following else root
        approach = next((p for p in (target - 1, target - 2, target + 1, target + 2) if p % 12 in scale and p != fifth),
                        target + 2)
        walk = (root, third, fifth, approach)
        return [Note(p, start + i, 1.0, _vel(velocity * (1.0 if i == 0 else 0.86))) for i, p in enumerate(walk)]
    raise ValueError(f"unknown bass line {line!r}")


def pad_bar(chord: Chord, ceiling: int, bar: int, velocity: int) -> list[Note]:
    """A wide, held voicing (root, fifth, the third an octave up), all of it under the ceiling."""
    root = _in_range(chord.root, PAD_LOW, PAD_LOW + 12)
    third = QUALITIES[chord.quality][1] if len(QUALITIES[chord.quality]) > 2 else 7
    spread = [root, root + 7, root + 12 + third]
    notes = [p for p in spread if p <= ceiling] or [_highest_at_most(chord.root, ceiling)]
    start = bar * BEATS_PER_BAR
    return [Note(p, start, 4.0, _vel(velocity)) for p in notes]


def _in_range(pitch_class: int, low: int, high: int) -> int:
    """The note of that pitch class in the octave from `low` (`high` is low + 12 everywhere here)."""
    assert high - low == 12
    return low + (pitch_class - low) % 12


def _highest_at_most(pitch_class: int, ceiling: int) -> int:
    return ceiling - (ceiling - pitch_class) % 12


def _movement(before: list[int], after: list[int]) -> int:
    a, b = sorted(before), sorted(after)
    if len(a) != len(b):
        return abs(sum(a) // len(a) - sum(b) // len(b)) * max(len(a), len(b))
    return sum(abs(x - y) for x, y in zip(a, b))


def _vel(value: float) -> int:
    return max(1, min(127, round(value)))
