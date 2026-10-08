"""Convert chords into MIDI pitch numbers and note voicings."""

from __future__ import annotations

from music21 import harmony

from hum.engine.accompanist.models.chord import Chord

# music21 quality -> chord-symbol suffix.
_QUALITY_SUFFIX = {
    "major": "",
    "minor": "m",
    "diminished": "dim",
    "augmented": "aug",
}

# Default octave for the accompaniment voicing (C3 = MIDI 48).
DEFAULT_OCTAVE = 3


def to_m21_root(root: str) -> str:
    """Normalize a root name to music21 spelling (flats use '-', not 'b').

    Our Chord model stores flats as 'b' (e.g. 'Bb') for readability, but
    music21 expects 'B-'. A trailing 'b' on a bare chord symbol is otherwise
    misread as an invalid abbreviation.
    """
    if len(root) > 1 and root[1] == "b":
        return root[0] + "-" + root[2:]
    return root


def chord_pitches(chord: Chord, octave: int = DEFAULT_OCTAVE) -> list[int]:
    """Return the chord's triad as MIDI pitch numbers, voiced from `octave`.

    The root is placed in the given octave and the remaining tones stacked
    above it (ascending), so C major in octave 3 -> [C3, E3, G3] = [48, 52, 55].

    Args:
        chord: The chord to voice.
        octave: Octave for the root (scientific pitch notation; C3 = MIDI 48).

    Returns:
        Ascending list of MIDI pitch numbers for root, third, fifth.
    """
    suffix = _QUALITY_SUFFIX.get(chord.quality, "")
    cs = harmony.ChordSymbol(to_m21_root(chord.root) + suffix)

    # Pitch classes in chord order (root, third, fifth).
    pcs = [p.pitchClass for p in cs.pitches]

    root_midi = (octave + 1) * 12 + pcs[0]  # C3 -> (3+1)*12 + 0 = 48
    pitches = [root_midi]
    for pc in pcs[1:]:
        # Stack each next tone at or above the previous one.
        candidate = (octave + 1) * 12 + pc
        while candidate <= pitches[-1]:
            candidate += 12
        pitches.append(candidate)
    return pitches


def pitch_names(chord: Chord, octave: int = DEFAULT_OCTAVE) -> list[str]:
    """Human-readable voicing, e.g. ['C3', 'E3', 'G3']."""
    from music21 import pitch as m21pitch

    names = []
    for midi in chord_pitches(chord, octave):
        p = m21pitch.Pitch(midi=midi)
        names.append(p.nameWithOctave.replace("-", "b"))
    return names
