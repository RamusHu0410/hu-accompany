"""Read MIDI files into music21 streams."""

from __future__ import annotations

from pathlib import Path

from music21 import converter, stream


def read_midi(path: str) -> stream.Score:
    """Parse a MIDI file into a music21 stream.

    Args:
        path: Path to a .mid file.

    Returns:
        A music21 Score (a Stream subclass) representing the MIDI file.

    Raises:
        FileNotFoundError: if the MIDI file does not exist.
    """
    if not Path(path).is_file():
        raise FileNotFoundError(f"MIDI file not found: {path}")

    return converter.parse(path)
