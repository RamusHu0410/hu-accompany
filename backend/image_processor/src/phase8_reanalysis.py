"""Phase 8 - Consistency & Re-analysis Engine.

Spec: when confidence falls below threshold or validation finds
contradictions, reprocess only the affected region (higher-res render,
alternate detector, retried OCR, ...) rather than the whole document.

Actually re-running oemer on a cropped/higher-res region isn't done here -
oemer takes on the order of a minute per full page even at its own working
resolution (see phase2_detect.py), so an automatic higher-res retry per
flagged measure would make failures more expensive than the initial pass,
for an OMR model that has no "try harder" mode to invoke anyway. What is
implemented is the one deterministic correction Phase 7's flags make
possible without re-detecting anything: if a measure's total duration is
off from the time signature by a ratio close to a small fraction (3/2, 2/3,
4/3, ...), that usually means an undetected tuplet scaled the written
durations by exactly that ratio - so rescale the stream to fit and mark it
corrected. Anything else stays flagged with lowered confidence rather than
guessed at.
"""

import logging
from fractions import Fraction
from collections import defaultdict

_MAX_DENOMINATOR = 8
_RATIO_TOLERANCE = 0.05
_LOW_CONFIDENCE = 0.5


def _plausible_ratio(actual: float, expected: float) -> "Fraction | None":
    if expected <= 0:
        return None
    ratio = actual / expected
    frac = Fraction(ratio).limit_denominator(_MAX_DENOMINATOR)
    if frac.numerator == 0:
        return None
    if abs(float(frac) - ratio) <= _RATIO_TOLERANCE:
        return frac
    return None


def reanalyze(structure: dict, config, logger: logging.Logger) -> dict:
    streams = defaultdict(list)
    for n in structure["notes"]:
        if "beat_total_mismatch" in n.get("validation_flags", []):
            streams[(n["measure"], n["part_index"], n["voice_index"])].append(n)

    corrected, unresolved = 0, 0
    for events in streams.values():
        expected = events[0]["expected_measure_ql"]
        actual = events[0]["actual_measure_ql"]
        ratio = _plausible_ratio(actual, expected)

        if ratio is not None and ratio != 1:
            scale = 1.0 / float(ratio)
            for e in events:
                e["duration_ql"] *= scale
                e["validation_flags"].remove("beat_total_mismatch")
                e["reanalysis_correction"] = f"rescaled by {scale:.4f} (measure total was {actual}/{expected} of expected)"
            corrected += 1
        else:
            for e in events:
                e["confidence"] = _LOW_CONFIDENCE
            unresolved += 1

    logger.info(
        "phase8_reanalysis: rescaled %d flagged measure-stream(s) via plausible-ratio correction, %d left flagged with low confidence",
        corrected, unresolved,
    )
    return structure
