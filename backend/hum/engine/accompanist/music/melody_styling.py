"""Stylize the melody itself to match an accompaniment style.

This only runs when melody editing is explicitly allowed. For jazz it applies
a swing feel (long-short eighth pairs), light syncopation, and occasional
grace-note approaches, so the melody sounds jazzy rather than mechanical.
"""

from __future__ import annotations

import random

from hum.engine.accompanist.music.scales import snap_pitch

# Swing: the on-beat note lengthens toward a triplet feel, the following
# off-beat note starts late and shortens.
_SWING_PUSH = 1.0 / 6.0   # how far an off-beat note is delayed (in beats)
_GRACE_CHANCE = 0.25      # chance of adding a quick grace note before a note
_GRACE_LEN = 0.12         # grace-note length in beats


def _is_offbeat(start: float) -> bool:
    """True if the note starts on an 'and' (halfway through a beat)."""
    frac = start - int(start)
    return abs(frac - 0.5) < 1e-6


def jazz_stylize(notes: list[dict], key: str, scale: str = "jazz") -> list[dict]:
    """Return a jazz-styled copy of the melody notes.

    Steps:
      1. Snap pitches to the jazz scale (bends chromatic notes to scale tones).
      2. Swing: delay off-beat notes slightly and lengthen on-beat notes for a
         long-short bounce.
      3. Occasionally add a chromatic grace note leading into a note.

    Timing stays in beats; pitches are MIDI numbers.
    """
    styled: list[dict] = []
    ordered = sorted(notes, key=lambda n: n["start"])

    for n in ordered:
        pitch = snap_pitch(int(n["pitch"]), key, scale)
        start = float(n["start"])
        dur = float(n["duration"])

        # Swing feel: nudge off-beat notes later; stretch on-beat notes a touch.
        if _is_offbeat(start):
            start += _SWING_PUSH
            dur = max(0.05, dur - _SWING_PUSH)
        else:
            dur = dur * 1.1  # slight lengthening of the "long" note

        # Optional grace note: a quick step below, snapped to scale, just ahead.
        if random.random() < _GRACE_CHANCE and start - _GRACE_LEN >= 0:
            grace_pitch = snap_pitch(pitch - 2, key, scale)
            if grace_pitch != pitch:
                styled.append({
                    "pitch": grace_pitch,
                    "start": start - _GRACE_LEN,
                    "duration": _GRACE_LEN,
                })

        styled.append({"pitch": pitch, "start": start, "duration": dur})

    styled.sort(key=lambda x: x["start"])
    return styled
