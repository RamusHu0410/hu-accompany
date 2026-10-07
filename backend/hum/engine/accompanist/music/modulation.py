"""Key modulation: transpose a melody into a different major/minor key.

Given a source key/mode and a target key/mode, this shifts every melody note
by the pitch interval between the two tonics. Switching mode (major <-> minor)
on the *same* tonic keeps the pitch level and only relabels the mode, so the
harmony engine picks minor/major diatonic chords accordingly.
"""

from __future__ import annotations

from music21 import pitch as m21pitch

# Valid mode names we accept.
_MODES = {"major", "minor"}


def _to_m21(name: str) -> str:
    """Normalize a tonic name to music21 spelling ('Bb' -> 'B-')."""
    if len(name) > 1 and name[1] == "b":
        return name[0] + "-" + name[2:]
    return name


def tonic_pitch_class(key: str) -> int:
    """Pitch class (0-11) of a key's tonic."""
    return m21pitch.Pitch(_to_m21(key)).pitchClass


def transpose_interval(from_key: str, to_key: str) -> int:
    """Semitone shift to move from one tonic to another (-6..+6, nearest)."""
    diff = (tonic_pitch_class(to_key) - tonic_pitch_class(from_key)) % 12
    # Pick the smaller direction so we don't leap an octave unnecessarily.
    if diff > 6:
        diff -= 12
    return diff


def modulate_notes(
    notes: list[dict],
    from_key: str,
    to_key: str,
) -> list[dict]:
    """Return a copy of the melody transposed from `from_key` to `to_key`.

    Timing is untouched; only pitches shift by the tonic interval.
    """
    shift = transpose_interval(from_key, to_key)
    if shift == 0:
        return [dict(n) for n in notes]
    out = []
    for n in notes:
        m = dict(n)
        m["pitch"] = int(n["pitch"]) + shift
        out.append(m)
    return out


def resolve_target(
    source_key: str,
    source_mode: str,
    target_key: str | None,
    target_mode: str | None,
) -> tuple[str, str, int]:
    """Work out the destination key/mode and the transpose interval.

    Args:
        source_key: The melody's current tonic.
        source_mode: The melody's current mode.
        target_key: Desired tonic (or None to keep the source tonic).
        target_mode: Desired mode (or None to keep the source mode).

    Returns:
        (target_key, target_mode, semitone_shift)
    """
    dest_key = target_key or source_key
    dest_mode = (target_mode or source_mode).lower()
    if dest_mode not in _MODES:
        raise ValueError(f"mode must be 'major' or 'minor', got '{dest_mode}'.")
    shift = transpose_interval(source_key, dest_key)
    return dest_key, dest_mode, shift
