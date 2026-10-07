"""Scale definitions and pitch-snapping.

Used by scale-flavored styles (jazz, asian_folk) to bend melody/accompaniment
pitches onto a target scale relative to a key's tonic.
"""

from __future__ import annotations

from music21 import pitch as m21pitch

# Scale interval sets, as semitone offsets from the tonic (pitch class 0).
SCALES: dict[str, list[int]] = {
    # Jazz "bebop major": the major scale (1 2 3 4 5 6 7) plus a passing b6.
    # Staying close to the major scale keeps the melody consonant with the
    # diatonic maj7/m7 comping instead of clashing like a raw blues b3 would.
    "jazz": [0, 2, 4, 5, 7, 8, 9, 11],     # major scale + added b6 color tone
    "blues": [0, 3, 5, 6, 7, 10],          # minor blues scale: 1 b3 4 b5 5 b7
    # Major pentatonic: 1 2 3 5 6  (common East-Asian folk sonority)
    "pentatonic": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
}


def tonic_pitch_class(key: str) -> int:
    """Pitch class (0-11) of a key's tonic. Accepts 'Bb' or 'B-' spellings."""
    spelled = key
    if len(key) > 1 and key[1] == "b":
        spelled = key[0] + "-" + key[2:]
    return m21pitch.Pitch(spelled).pitchClass


def scale_pitch_classes(key: str, scale: str) -> set[int]:
    """The allowed pitch classes for `scale` in `key`."""
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'. Choose from: {sorted(SCALES)}")
    tonic = tonic_pitch_class(key)
    return {(tonic + iv) % 12 for iv in SCALES[scale]}


def snap_pitch(midi_pitch: int, key: str, scale: str) -> int:
    """Snap a MIDI pitch to the nearest pitch in `scale` (relative to `key`).

    Preserves octave placement: the result is the closest scale pitch, breaking
    ties downward (toward the lower pitch) for a stable, predictable feel.

    Args:
        midi_pitch: The pitch to snap.
        key: Tonic note name (e.g. "C").
        scale: A key in SCALES ("jazz", "blues", "pentatonic", ...).

    Returns:
        A MIDI pitch whose pitch class is in the scale.
    """
    allowed = scale_pitch_classes(key, scale)
    if midi_pitch % 12 in allowed:
        return midi_pitch

    # Search outward from the original pitch for the nearest allowed pitch.
    for delta in range(1, 7):
        if (midi_pitch - delta) % 12 in allowed:
            down = midi_pitch - delta
        else:
            down = None
        if (midi_pitch + delta) % 12 in allowed:
            up = midi_pitch + delta
        else:
            up = None
        # Prefer the downward move on ties for a stable, grounded sound.
        if down is not None:
            return down
        if up is not None:
            return up
    return midi_pitch  # should never happen for non-empty scales


def snap_notes(notes: list[dict], key: str, scale: str) -> list[dict]:
    """Return a copy of melody note dicts with pitches snapped to `scale`."""
    snapped = []
    for n in notes:
        m = dict(n)
        m["pitch"] = snap_pitch(int(n["pitch"]), key, scale)
        snapped.append(m)
    return snapped
