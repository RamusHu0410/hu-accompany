"""Phase 9 - Timeline Generation.

Spec: convert validated notation into chronological NoteEvent records
(frequency, start time, duration, dynamic, measure, beat, voice).

Converts Phase 5-8's quarter-length offsets into seconds using a tempo map
built from Phase 4's OCR tempo markings (falling back to DEFAULT_BPM where
none were found - oemer itself never provides a tempo), and dynamics from
Phase 4's OCR dynamic markings (falling back to DEFAULT_DYNAMIC). Both maps
are piecewise-constant step functions in offset_ql; conversion to seconds
integrates across tempo changes rather than assuming one constant tempo for
the whole piece. Chords explode into one NoteEvent per pitch, all sharing
the same start/duration, matching the flat (non-chord-grouped) notes.json
schema. Rests produce no NoteEvent - notes.json is a list of sounding
notes, not a transcription of silence.
"""

import logging

from .models.timeline import NoteEvent

DEFAULT_BPM = 120.0
DEFAULT_DYNAMIC = 0.6


def _measure_start_offsets(notes: list) -> dict:
    """measure number -> offset_ql of that measure's beat 0, derived from any
    note in it (offset_ql - beat is constant for all notes sharing a measure)."""
    starts = {}
    for n in notes:
        starts.setdefault(n["measure"], n["offset_ql"] - n["beat"])
    return starts


def _marking_offsets_ql(markings: list, measure_starts: dict, avg_measure_ql: float) -> list:
    """Resolves each marking's (measure, beat) into an absolute offset_ql.
    Falls back to an evenly-spaced estimate for the rare measure with no
    notes at all to anchor against."""
    resolved = []
    for mk in markings:
        start = measure_starts.get(mk["measure"])
        if start is None:
            start = (mk["measure"] - 1) * avg_measure_ql
        resolved.append((start + mk["beat"], mk))
    return resolved


def _build_step_map(markings: list, measure_starts: dict, avg_measure_ql: float,
                     marking_type: str, value_default: float) -> list:
    points = [(0.0, value_default)]
    for offset_ql, mk in _marking_offsets_ql(markings, measure_starts, avg_measure_ql):
        if mk["type"] == marking_type:
            points.append((offset_ql, mk["value"]))
    points.sort(key=lambda p: p[0])
    return points


def _value_at(step_map: list, offset_ql: float):
    value = step_map[0][1]
    for point_ql, point_value in step_map:
        if point_ql > offset_ql:
            break
        value = point_value
    return value


def _ql_to_seconds(offset_ql: float, tempo_map: list) -> float:
    """Integrates across tempo breakpoints (in quarter-length units, bpm =
    quarter notes per minute) up to `offset_ql`."""
    seconds = 0.0
    for i, (point_ql, bpm) in enumerate(tempo_map):
        if point_ql >= offset_ql:
            break
        segment_end = tempo_map[i + 1][0] if i + 1 < len(tempo_map) else offset_ql
        segment_end = min(segment_end, offset_ql)
        seconds += max(segment_end - point_ql, 0.0) * 60.0 / bpm
    return seconds


def generate_timeline(structure: dict, config, logger: logging.Logger) -> list:
    notes = structure["notes"]
    markings = structure["markings"]
    numerator, denominator = structure["time_signature"]
    avg_measure_ql = numerator * (4.0 / denominator)
    measure_starts = _measure_start_offsets(notes)

    tempo_map = _build_step_map(markings, measure_starts, avg_measure_ql, "tempo", DEFAULT_BPM)
    dynamic_map = _build_step_map(markings, measure_starts, avg_measure_ql, "dynamic", DEFAULT_DYNAMIC)

    events: list[NoteEvent] = []
    next_id = 1
    for n in sorted(notes, key=lambda n: n["offset_ql"]):
        if not n["pitches_hz"]:
            continue  # rest - no sounding note to emit

        start = _ql_to_seconds(n["offset_ql"], tempo_map)
        end = _ql_to_seconds(n["offset_ql"] + n["duration_ql"], tempo_map)
        dynamic = _value_at(dynamic_map, n["offset_ql"])
        voice = n["part_index"] * 10 + n["voice_index"]

        for hz in n["pitches_hz"]:
            events.append(NoteEvent(
                id=next_id,
                hz=round(hz, 3),
                start=round(start, 4),
                duration=round(max(end - start, 0.0), 4),
                dynamic=round(dynamic, 3),
                measure=n["measure"],
                beat=round(n["beat"], 3),
                voice=voice,
            ))
            next_id += 1

    logger.info(
        "phase9_timeline: generated %d note events (%d tempo change(s), %d dynamic change(s))",
        len(events), len(tempo_map) - 1, len(dynamic_map) - 1,
    )
    return events
