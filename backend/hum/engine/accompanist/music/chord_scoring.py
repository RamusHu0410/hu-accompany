"""Score how well a chord fits a set of melody notes."""

from __future__ import annotations

from music21 import key as m21key

from hum.engine.accompanist.models.chord import Chord

# Scoring weights.
CHORD_TONE = 2      # melody note is a chord tone (root/third/fifth)
SCALE_TONE = 1      # melody note is in the key's scale but not a chord tone
CLASH = -2          # melody note is outside the scale (strong clash)

# music21 quality -> chord-symbol pitch spelling helper.
_QUALITY_TO_M21 = {
    "major": "",
    "minor": "m",
    "diminished": "dim",
    "augmented": "aug",
}


def _chord_pitch_classes(chord: Chord) -> set[int]:
    """Pitch classes of the chord's tones (root, third, fifth)."""
    from music21 import harmony

    from hum.engine.accompanist.music.chord_to_midi import to_m21_root

    quality = _QUALITY_TO_M21.get(chord.quality, "")
    cs = harmony.ChordSymbol(to_m21_root(chord.root) + quality)
    return {p.midi % 12 for p in cs.pitches}


def score_chord(chord: Chord, melody_notes: list[int], key: str = "C",
                mode: str = "major") -> int:
    """Score a chord against melody notes.

    Args:
        chord: Candidate chord.
        melody_notes: Melody pitches as MIDI numbers.
        key: Tonic of the surrounding key (for scale-tone checks).
        mode: "major" or "minor".

    Returns:
        Integer score. Higher means the chord fits the melody better.
    """
    chord_pcs = _chord_pitch_classes(chord)
    scale_pcs = {p.midi % 12 for p in m21key.Key(key, mode).pitches}

    score = 0
    for pc in _melody_pitch_classes(melody_notes):
        if pc in chord_pcs:
            score += CHORD_TONE
        elif pc in scale_pcs:
            score += SCALE_TONE
        else:
            score += CLASH
    return score


def _melody_pitch_classes(melody_notes: list[int]) -> list[int]:
    """Melody MIDI notes reduced to pitch classes, preserving repeats."""
    return [n % 12 for n in melody_notes]
