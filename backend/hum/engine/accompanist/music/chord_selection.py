"""Choose the best-fitting chord for a melody segment."""

from __future__ import annotations

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_candidates import get_candidates
from hum.engine.accompanist.music.chord_scoring import score_chord, _chord_pitch_classes


def choose_best_chord(melody_notes: list[int], key: str = "C",
                      mode: str = "major") -> Chord:
    """Pick the diatonic chord that best fits the melody notes.

    Scores every diatonic candidate and returns the highest scorer. Ties are
    broken by preferring the chord whose root appears in the melody, then by
    the chord that covers the most distinct melody pitch classes.

    Args:
        melody_notes: Melody pitches as MIDI numbers.
        key: Tonic of the surrounding key.
        mode: "major" or "minor".

    Returns:
        The best-fitting Chord.
    """
    candidates = get_candidates(key, mode)
    melody_pcs = {n % 12 for n in melody_notes}

    def rank(chord: Chord):
        base = score_chord(chord, melody_notes, key, mode)
        chord_pcs = _chord_pitch_classes(chord)
        root_in_melody = 1 if _root_pc(chord) in melody_pcs else 0
        coverage = len(melody_pcs & chord_pcs)
        return (base, root_in_melody, coverage)

    return max(candidates, key=rank)


def _root_pc(chord: Chord) -> int:
    """Pitch class of the chord root."""
    from music21 import pitch as m21pitch

    return m21pitch.Pitch(chord.root).midi % 12
