"""The one place where the hum's notes (seconds) become the accompanist's melody (beats).

The audio side measures time in seconds; ``accompanist.generate_accompaniment`` counts beats and
lays one or two chords over every four of them. Converting in several places is how the upload
route came to hand the engine seconds as if they were beats (so the song played at the wrong
speed). Everything that feeds the engine goes through ``to_engine_melody``:

    1. the first note becomes beat 0 (the silence before the hum isn't part of the tune),
    2. seconds become beats at the hum's tempo,
    3. starts and ends snap to a sixteenth-note grid, so the chords line up with the notes,
    4. no note overlaps the next or is shorter than one grid step.
"""

GRID_BEATS = 0.25  # a sixteenth note; None keeps the timing exactly as hummed
DEFAULT_TEMPO = 100.0  # used when the hum's tempo can't be measured
SENSIBLE_TEMPO = (40.0, 220.0)


def sensible_tempo(tempo: float | None) -> float:
    """The hum's tempo if it was measured and plausible, else DEFAULT_TEMPO."""
    tempo = tempo or 0.0
    return tempo if SENSIBLE_TEMPO[0] <= tempo <= SENSIBLE_TEMPO[1] else DEFAULT_TEMPO


def to_engine_melody(
    melody: list[dict],
    tempo: float,
    grid: float | None = GRID_BEATS,
    shift: float = 0.0,
) -> list[dict]:
    """The accompanist's melody: {hz (MIDI note), start, duration} in beats.

    Args:
        melody: The hum's notes from ``analyze_audio_file``: hz (MIDI), start and duration in seconds.
        tempo: Beats per minute to count the seconds in.
        grid: Snap starts and ends to multiples of this many beats (None to keep them as hummed).
        shift: Semitones to move every note by (kept within MIDI 0-127).
    """
    if not melody:
        return []
    notes = sorted(melody, key=lambda n: n["start"])
    first = notes[0]["start"]
    beats_per_second = tempo / 60.0
    out = []
    for note in notes:
        start = (note["start"] - first) * beats_per_second
        end = start + note["duration"] * beats_per_second
        if grid:
            start, end = round(start / grid) * grid, round(end / grid) * grid
            if out and start < out[-1]["start"] + grid:  # two notes snapped onto one step
                start = out[-1]["start"] + grid
            end = max(end, start + grid)
        if out and out[-1]["start"] + out[-1]["duration"] > start:
            out[-1]["duration"] = start - out[-1]["start"]  # the earlier note stops as the next begins
        out.append({"hz": min(127.0, max(0.0, note["hz"] + shift)), "start": start, "duration": end - start})
    return [{**n, "start": round(n["start"], 4), "duration": round(n["duration"], 4)} for n in out]


def seconds_from_engine(melody: list[dict], tempo: float, offset: float = 0.0) -> list[dict]:
    """Beats back to seconds on the hum's own time axis (for drawing both on one graph)."""
    seconds_per_beat = 60.0 / tempo
    return [
        {"hz": n["hz"], "start": offset + n["start"] * seconds_per_beat, "duration": n["duration"] * seconds_per_beat}
        for n in melody
    ]
