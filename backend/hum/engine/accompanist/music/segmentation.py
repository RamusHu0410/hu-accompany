"""Divide a melody into per-bar segments (MVP: one chord slot per bar)."""

from __future__ import annotations

# Beats per bar in 4/4, measured in quarter lengths.
DEFAULT_BEATS_PER_BAR = 4.0


def segment_by_bar(
    melody_notes: list[dict],
    beats_per_bar: float = DEFAULT_BEATS_PER_BAR,
    num_bars: int | None = None,
) -> list[list[dict]]:
    """Split melody notes into one bucket per bar.

    A note is assigned to a bar by its start time. This is the MVP "one chord
    per bar" segmentation.

    Args:
        melody_notes: Notes as dicts with "pitch"/"start"/"duration"
            (start/duration in quarter lengths).
        beats_per_bar: Bar length in quarter lengths (default 4 = 4/4).
        num_bars: Force this many segments. If None, inferred from the last
            note's end time.

    Returns:
        A list of segments; each segment is a list of note dicts. Segments may
        be empty if a bar has no note onset.
    """
    if num_bars is None:
        if not melody_notes:
            return []
        last_end = max(n["start"] + n["duration"] for n in melody_notes)
        # Number of bars needed to contain the last note's end.
        num_bars = max(1, _ceil_div(last_end, beats_per_bar))

    segments: list[list[dict]] = [[] for _ in range(num_bars)]
    for note in melody_notes:
        bar_index = int(note["start"] // beats_per_bar)
        if 0 <= bar_index < num_bars:
            segments[bar_index].append(note)

    return segments


def segment_by_slot(
    melody_notes: list[dict],
    slot_beats: float,
    num_slots: int | None = None,
) -> list[list[dict]]:
    """Split melody notes into fixed-length slots of `slot_beats` each.

    Generalizes segment_by_bar to any harmonic-rhythm resolution. For example
    slot_beats=2 gives two chord slots per 4/4 bar, so the harmony can change
    mid-bar when the melody does.

    A note is assigned to the slot its start time falls in. Notes are also
    counted into any later slot they sustain through, so a chord slot "sees"
    notes held over from earlier — this keeps sustained notes influencing the
    harmony of the slot they ring during.
    """
    if num_slots is None:
        if not melody_notes:
            return []
        last_end = max(n["start"] + n["duration"] for n in melody_notes)
        num_slots = max(1, _ceil_div(last_end, slot_beats))

    segments: list[list[dict]] = [[] for _ in range(num_slots)]
    for note in melody_notes:
        start = note["start"]
        end = start + note["duration"]
        first = int(start // slot_beats)
        # last slot the note still sounds in (exclusive end handled by -eps)
        last = int((end - 1e-6) // slot_beats)
        for s in range(max(0, first), min(last, num_slots - 1) + 1):
            if 0 <= s < num_slots:
                segments[s].append(note)

    return segments


def _ceil_div(a: float, b: float) -> int:
    """Ceiling of a / b, tolerant of floating-point noise."""
    import math

    return int(math.ceil(round(a / b, 6)))
