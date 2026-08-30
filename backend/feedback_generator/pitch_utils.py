"""Small pitch-math helpers shared by alignment.py, analysis.py, and nlg.py."""

import math

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
A4_HZ = 440.0
A4_MIDI = 69


def hz_to_cents(user_hz: float, expected_hz: float) -> float:
    """Signed distance in cents (1/100th of a semitone) from expected_hz to
    user_hz. Positive = user played sharp/higher than expected."""
    return 1200 * math.log2(user_hz / expected_hz)


def hz_to_midi(hz: float) -> float:
    return A4_MIDI + 12 * math.log2(hz / A4_HZ)


def hz_to_note_name(hz: float) -> str:
    """Nearest note name (e.g. "F#4") for a frequency, rounded to the nearest semitone."""
    midi = round(hz_to_midi(hz))
    name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"
