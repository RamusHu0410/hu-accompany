"""Generate diatonic chord candidates for a given key."""

from __future__ import annotations

from music21 import roman
from music21 import key as m21key

from hum.engine.accompanist.models.chord import Chord

# Roman-numeral degrees for the seven diatonic triads.
# Major: I ii iii IV V vi vii°  (vii is diminished -> "viio")
# Minor: i ii° III iv v VI VII   (natural minor)
_DEGREES_MAJOR = ["I", "ii", "iii", "IV", "V", "vi", "viio"]
_DEGREES_MINOR = ["i", "iio", "III", "iv", "v", "VI", "VII"]

# Map music21's commonName to our quality vocabulary.
_QUALITY_MAP = {
    "major triad": "major",
    "minor triad": "minor",
    "diminished triad": "diminished",
    "augmented triad": "augmented",
}


def get_candidates(key: str = "C", mode: str = "major") -> list[Chord]:
    """Return the seven diatonic triads of a key.

    Args:
        key: Tonic note name (e.g. "C", "A", "F#").
        mode: "major" or "minor".

    Returns:
        A list of seven Chord objects in scale-degree order (I..vii).
    """
    tonic_key = m21key.Key(key, mode)
    degrees = _DEGREES_MINOR if mode == "minor" else _DEGREES_MAJOR
    chords: list[Chord] = []

    for degree in degrees:
        rn = roman.RomanNumeral(degree, tonic_key)
        root = rn.root().name.replace("-", "b")  # music21 uses '-' for flats
        quality = _QUALITY_MAP.get(rn.commonName, rn.quality)
        chords.append(Chord(root=root, quality=quality))

    return chords
