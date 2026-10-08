"""Extract melody notes from a music21 stream into plain dicts."""

from __future__ import annotations

from music21 import stream


def extract_melody(score: stream.Stream) -> list[dict]:
    """Extract melody notes from a music21 stream.

    Each note becomes a dict with:
        pitch:    MIDI pitch number (int)
        start:    onset offset in quarter lengths (float)
        duration: length in quarter lengths (float)

    Notes are returned ordered by start time. Chords are flattened to their
    individual pitches (each sharing the chord's start and duration).

    Args:
        score: A parsed music21 stream (e.g. from read_midi).

    Returns:
        A list of note dicts sorted by start time.
    """
    notes: list[dict] = []

    # flatten() collapses nested parts/measures so offsets are absolute.
    for element in score.flatten().notes:
        start = float(element.offset)
        duration = float(element.duration.quarterLength)

        if element.isChord:
            for p in element.pitches:
                notes.append(
                    {"pitch": int(p.midi), "start": start, "duration": duration}
                )
        else:
            notes.append(
                {
                    "pitch": int(element.pitch.midi),
                    "start": start,
                    "duration": duration,
                }
            )

    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    return notes
