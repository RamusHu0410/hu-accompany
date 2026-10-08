"""Convert a Melody into a MIDI file."""
# This is used for future steps

from __future__ import annotations

import pretty_midi

from hum.engine.accompanist.models.melody import Melody

# Default program: 0 = Acoustic Grand Piano (General MIDI).
DEFAULT_PROGRAM = 0
DEFAULT_VELOCITY = 100


def melody_to_midi(
    melody: Melody,
    path: str,
    *,
    program: int = DEFAULT_PROGRAM,
    velocity: int = DEFAULT_VELOCITY,
) -> str:
    """Write a Melody out to a MIDI file.

    Each Note's ``hz`` field is interpreted as a MIDI pitch number
    (e.g. 60 = middle C), ``start`` as the note-on time in seconds, and
    ``duration`` as the note length in seconds.

    Args:
        melody: The melody to render.
        path: Destination path for the ``.mid`` file.
        program: General MIDI program number for the instrument.
        velocity: Note-on velocity (0-127).

    Returns:
        The path the file was written to.
    """
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(melody.tempo))
    instrument = pretty_midi.Instrument(program=program)

    for note in melody.notes:
        pitch = int(round(note.hz))
        start = float(note.start)
        end = start + float(note.duration)
        instrument.notes.append(
            pretty_midi.Note(
                velocity=velocity,
                pitch=pitch,
                start=start,
                end=end,
            )
        )

    pm.instruments.append(instrument)
    pm.write(path)
    return path
