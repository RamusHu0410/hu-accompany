"""Detect the musical key of a MIDI file using music21."""

from __future__ import annotations

from pathlib import Path

from music21 import key as m21key
from music21 import note as m21note
from music21 import stream as m21stream

from hum.engine.accompanist.music.midi_reader import read_midi


def detect_key(midi_path: str) -> m21key.Key:
    """Detect the key of a MIDI file.

    Uses music21's Krumhansl-Schmuckler key-finding algorithm over the whole
    score.

    Args:
        midi_path: Path to a .mid file.

    Returns:
        A music21 Key object (e.g. str(result) == "C major" or "A minor").

    Raises:
        FileNotFoundError: if the MIDI file does not exist.
    """
    if not Path(midi_path).is_file():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    score = read_midi(midi_path)
    return score.analyze("key")


def detect_key_from_notes(melody_notes: list[dict]) -> m21key.Key:
    """Detect the key from melody note dicts (pitch/start/duration).

    Builds a music21 stream from the notes and runs the same
    Krumhansl-Schmuckler analysis used by detect_key.

    Args:
        melody_notes: Notes as dicts with "pitch"/"start"/"duration".

    Returns:
        A music21 Key object.
    """
    s = m21stream.Stream()
    for n in sorted(melody_notes, key=lambda x: x["start"]):
        m21n = m21note.Note(int(n["pitch"]))
        m21n.quarterLength = float(n["duration"]) or 1.0
        s.append(m21n)
    return s.analyze("key")
