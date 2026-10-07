"""Voice leading: re-voice a chord sequence to minimize melodic movement.

Given a progression, each chord can be voiced in several inversions/octaves.
We pick, for each chord after the first, the voicing (among a set of candidate
inversions across nearby octaves) that is closest to the previous voicing,
minimizing the total semitone movement between voices.
"""

from __future__ import annotations

from itertools import product

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_to_midi import chord_pitches


def _inversions(pitches: list[int], octave_span: int = 1) -> list[list[int]]:
    """Generate candidate voicings: all inversions across a few octaves.

    Each voicing keeps the same pitch classes. We rotate the chord (inversions)
    and also shift the whole thing up/down by octaves within +/- octave_span.
    """
    n = len(pitches)
    base = sorted(pitches)
    candidates: list[list[int]] = []

    for shift in range(-octave_span, octave_span + 1):
        shifted = [p + 12 * shift for p in base]
        # All inversions: move the lowest voice up an octave repeatedly.
        inv = sorted(shifted)
        for _ in range(n):
            candidates.append(list(inv))
            lowest = inv[0]
            inv = sorted(inv[1:] + [lowest + 12])
    # Deduplicate.
    unique = []
    seen = set()
    for c in candidates:
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def voicing_distance(a: list[int], b: list[int]) -> int:
    """Total semitone movement between two equal-size voicings (sorted match)."""
    a_sorted = sorted(a)
    b_sorted = sorted(b)
    return sum(abs(x - y) for x, y in zip(a_sorted, b_sorted))


def total_movement(voicings: list[list[int]]) -> int:
    """Sum of semitone movement across a whole sequence of voicings."""
    return sum(
        voicing_distance(voicings[i - 1], voicings[i])
        for i in range(1, len(voicings))
    )


def naive_voicings(chords: list[Chord], octave: int = 4) -> list[list[int]]:
    """Voicings with every chord in root position at the same octave."""
    return [chord_pitches(c, octave) for c in chords]


def lead_voices(chords: list[Chord], octave: int = 4,
                octave_span: int = 1) -> list[list[int]]:
    """Re-voice a progression to minimize movement between adjacent chords.

    The first chord stays in root position at `octave`; each subsequent chord
    is voiced (via inversion/octave choice) to sit as close as possible to the
    previous chord.

    Args:
        chords: The progression.
        octave: Root octave for the first chord.
        octave_span: How many octaves up/down to consider for candidates.

    Returns:
        A list of voicings (each a list of MIDI pitches).
    """
    if not chords:
        return []

    result = [chord_pitches(chords[0], octave)]
    for chord in chords[1:]:
        prev = result[-1]
        candidates = _inversions(chord_pitches(chord, octave), octave_span)
        best = min(candidates, key=lambda v: voicing_distance(prev, v))
        result.append(best)
    return result
