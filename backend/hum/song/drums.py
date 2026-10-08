"""Drum parts: one groove per genre, played lighter or fuller by section.

A groove is a bar of sixteenth-note steps per drum. In the patterns, X is an accent, x a normal hit,
o a soft one and . a rest. Swing is not written here: the renderer swings every track's off-beat
eighths together, so the drums and the band always agree.
"""

from .project import BEATS_PER_BAR, Note

STEPS = 16
STEP = BEATS_PER_BAR / STEPS
VELOCITY = {"X": 112, "x": 92, "o": 58}

KICK, SIDE_STICK, SNARE, CLAP, CLOSED_HAT, PEDAL_HAT, OPEN_HAT = 36, 37, 38, 39, 42, 44, 46
LOW_TOM, MID_TOM, HIGH_TOM, CRASH, RIDE, TAMBOURINE, SHAKER = 45, 47, 50, 49, 51, 54, 70
FLOOR_TOM = 41

# groove -> intensity (1 light, 2 full) -> {drum: pattern}
GROOVES = {
    "pop": {
        1: {KICK: "x.......x.......", SIDE_STICK: "....o.......o...", CLOSED_HAT: "o.o.o.o.o.o.o.o."},
        2: {KICK: "x.....x.x.......", SNARE: "....X.......X...", CLOSED_HAT: "x.o.x.o.x.o.x.o."},
    },
    "lofi": {
        1: {KICK: "x......o..x.....", SNARE: "....o.......o...", CLOSED_HAT: "o.o.o.o.o.o.o.o."},
        2: {KICK: "x......x.x......", SNARE: "....x.......x..o", CLOSED_HAT: "x.o.x.o.x.o.x.o."},
    },
    "rock": {
        1: {KICK: "x.......x.......", SNARE: "....x.......x...", CLOSED_HAT: "x.x.x.x.x.x.x.x."},
        2: {KICK: "x.....x.x.x.....", SNARE: "....X.......X...", RIDE: "x.x.x.x.x.x.x.x."},
    },
    "ballad": {
        1: {KICK: "o.......o.......", SIDE_STICK: "....o.......o..."},
        2: {KICK: "x.......x.o.....", SNARE: "....x.......x...", CLOSED_HAT: "o.o.o.o.o.o.o.o."},
    },
    "cinematic": {
        1: {FLOOR_TOM: "x.......x.......", KICK: "o..............."},
        2: {KICK: "x.....x.x.......", FLOOR_TOM: "x..x..x.x..x..x.", SNARE: "....x.......x..."},
    },
    "electronic": {
        1: {KICK: "x...x...x...x...", CLOSED_HAT: "..o...o...o...o."},
        2: {KICK: "X...x...X...x...", CLAP: "....x.......x...", OPEN_HAT: "..x...x...x...x.", CLOSED_HAT: "o.o.o.o.o.o.o.o."},
    },
    "jazz": {
        1: {RIDE: "o...o.o.o...o.o.", PEDAL_HAT: "....o.......o..."},
        2: {RIDE: "x...x.o.x...x.o.", PEDAL_HAT: "....x.......x...", KICK: "o...o...o...o...", SNARE: "......o.......o."},
    },
    "acoustic": {
        1: {SHAKER: "o.o.o.o.o.o.o.o.", KICK: "o.......o......."},
        2: {SHAKER: "x.o.x.o.x.o.x.o.", KICK: "x.......x.x.....", SIDE_STICK: "....x.......x...", TAMBOURINE: "....o.......o..."},
    },
}
# The last bar before a fuller section: the last beat becomes this.
FILLS = {
    "rock": {HIGH_TOM: "............x...", MID_TOM: ".............x..", LOW_TOM: "..............x.", FLOOR_TOM: "...............x"},
    "cinematic": {FLOOR_TOM: "............xxXX"},
    "jazz": {SNARE: "............o.xo"},
    "acoustic": {TAMBOURINE: "............xxxx"},
}
DEFAULT_FILL = {SNARE: "............o.xX"}


def drum_bar(groove: str, intensity: int, bar: int, *, crash: bool = False, fill: bool = False,
             velocity_shift: int = 0) -> list[Note]:
    """One bar of the groove starting at `bar`. Intensity 0 plays nothing."""
    if intensity <= 0:
        return []
    patterns = dict(GROOVES[groove][min(intensity, 2)])
    if fill:
        fill_patterns = FILLS.get(groove, DEFAULT_FILL)
        for drum in patterns:  # make room for the fill on the last beat
            patterns[drum] = patterns[drum][:12] + ("o..." if drum == KICK else "....")
        for drum, pattern in fill_patterns.items():
            patterns[drum] = _merge(patterns.get(drum, "." * STEPS), pattern)
    if crash:
        patterns[CRASH] = "X" + "." * (STEPS - 1)
    start = bar * BEATS_PER_BAR
    notes = []
    for drum, pattern in patterns.items():
        for step, mark in enumerate(pattern):
            if mark in VELOCITY:
                velocity = max(1, min(127, VELOCITY[mark] + velocity_shift))
                notes.append(Note(drum, start + step * STEP, STEP, velocity))
    return sorted(notes, key=lambda n: (n.start, n.pitch))


def end_hit(bar: int, velocity_shift: int = 0) -> list[Note]:
    """The last chord's hit: a kick and a crash on the downbeat, then let it ring."""
    velocity = max(1, min(127, VELOCITY["X"] + velocity_shift))
    start = bar * BEATS_PER_BAR
    return [Note(KICK, start, STEP, velocity), Note(CRASH, start, STEP, velocity)]


def _merge(base: str, over: str) -> str:
    return "".join(o if o != "." else b for b, o in zip(base, over))
