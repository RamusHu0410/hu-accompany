"""Phase 7 - Music Theory Validation.

Spec: verify reconstructed music (measure duration, beat totals, key/clef
consistency, chord/voice consistency, ...), attempt deterministic
corrections, and lower confidence where uncertain.

Deterministic correction itself is Phase 8's job (it needs the validation
flags this phase produces); this phase only detects and records the two
checks that are actually computable from Phase 5's structure without pixel
access: whether each (measure, part, voice) stream's note/rest durations
sum to the inferred time signature's beat total, and whether any two
events in the same voice overlap in time (they shouldn't - a single voice
is monophonic by construction, so overlap means a detection error, not a
real musical situation). Tie/slur/hairpin/pedal/ottava consistency checks
from the design doc are not implemented - this pipeline never detects those
markings in the first place (see phase5_reasoning.py's docstring), so
there's nothing to validate.
"""

import logging
from collections import defaultdict

_TOLERANCE_QL = 0.1


def _expected_measure_ql(time_signature: tuple) -> float:
    numerator, denominator = time_signature
    return numerator * (4.0 / denominator)


def _group_by_stream(notes: list) -> dict:
    groups = defaultdict(list)
    for n in notes:
        groups[(n["measure"], n["part_index"], n["voice_index"])].append(n)
    return groups


def validate(structure: dict, config, logger: logging.Logger) -> dict:
    expected_ql = _expected_measure_ql(structure["time_signature"])
    streams = _group_by_stream(structure["notes"])

    validations = []
    mismatches = 0
    overlaps = 0

    for (measure, part_index, voice_index), events in streams.items():
        actual_ql = round(sum(e["duration_ql"] for e in events), 4)
        ok = abs(actual_ql - expected_ql) <= _TOLERANCE_QL
        if not ok:
            mismatches += 1
            for e in events:
                e.setdefault("validation_flags", []).append("beat_total_mismatch")
                e["expected_measure_ql"] = expected_ql
                e["actual_measure_ql"] = actual_ql

        events_sorted = sorted(events, key=lambda e: e["beat"])
        for a, b in zip(events_sorted, events_sorted[1:]):
            if a["beat"] + a["duration_ql"] > b["beat"] + _TOLERANCE_QL:
                overlaps += 1
                a.setdefault("validation_flags", []).append("voice_overlap")
                b.setdefault("validation_flags", []).append("voice_overlap")

        validations.append({
            "measure": measure, "part_index": part_index, "voice_index": voice_index,
            "expected_ql": expected_ql, "actual_ql": actual_ql, "ok": ok,
        })

    structure["validation"] = validations
    logger.info(
        "phase7_validation: %d/%d (measure, part, voice) streams match the inferred time signature; %d overlap(s) flagged",
        len(validations) - mismatches, len(validations), overlaps,
    )
    return structure
