"""
Anchor OCR'd marking candidates (see ocr_detect.py) to a quarter-length
offset in the page's music21 timeline, using barline x positions -- the same
coordinate space oemer's own bboxes (noteheads, barlines, etc.) already live
in. Callers are expected to have already rescaled each marking's bbox into
that coordinate space (see detect.py) before calling `anchor()`.

Position is inferred by finding which pair of barlines a marking's x
position falls between, then interpolating linearly across that measure's
quarter-length span. That's an approximation, not an exact readout --
engraving spaces notes/text roughly proportionally to their duration, not
exactly -- but it's precise enough to place a marking within the right
measure and roughly the right beat.

Ported from an earlier prototype's `phase5_reasoning.py::_anchor_markings`,
adapted to re-parse the page's own MusicXML directly (cheap -- these are
single-page documents) instead of carrying a separate measure/offset
bookkeeping structure across phases.
"""

import music21


def _measure_offsets(xml_path: str) -> dict:
    """number -> (offset_ql, duration_ql) for every measure in the page's
    first part (measure numbering/duration is shared across parts in a
    stitched score, e.g. a piano grand staff's treble and bass staves)."""
    score = music21.converter.parse(xml_path)
    part = score.parts[0]
    return {
        m.number: (float(m.offset), float(m.barDuration.quarterLength))
        for m in part.getElementsByClass("Measure")
    }


def anchor(markings: list, barlines: list, xml_path: str) -> list:
    """
    `markings` bboxes must already be in oemer's working-image coordinate
    space (the same space `barlines` is in).

    Returns [{"offset_ql", "type", "value", "text", "confidence"}, ...],
    sorted by offset_ql, page-local (starts near 0 -- the caller is
    responsible for offsetting multi-page pieces onto one timeline).
    """
    if not markings:
        return []

    measures = _measure_offsets(xml_path)
    if not measures:
        return []
    avg_measure_ql = sum(d for _, d in measures.values()) / len(measures)

    barline_xs = sorted(x1 + (x2 - x1) / 2 for x1, _, x2, _ in barlines)

    anchored = []
    for mk in markings:
        x1, _, x2, _ = mk["bbox"]
        cx = (x1 + x2) / 2

        if not barline_xs:
            local_measure, fraction = 1, 0.0
        else:
            idx = 0
            while idx < len(barline_xs) and barline_xs[idx] <= cx:
                idx += 1
            local_measure = idx + 1
            left = barline_xs[idx - 1] if idx > 0 else barline_xs[0] - 200
            right = barline_xs[idx] if idx < len(barline_xs) else left + 200
            span = max(right - left, 1.0)
            fraction = max(0.0, min(1.0, (cx - left) / span))

        offset_ql, duration_ql = measures.get(local_measure, (None, None))
        if offset_ql is None:
            # Ran past the last measure music21 parsed (e.g. a marking sitting
            # after the final barline) -- extrapolate using the average.
            offset_ql = (local_measure - 1) * avg_measure_ql
            duration_ql = avg_measure_ql

        anchored.append({
            "offset_ql": round(offset_ql + fraction * duration_ql, 4),
            "type": mk["type"],
            "value": mk["value"],
            "text": mk["text"],
            "confidence": mk["confidence"],
        })

    anchored.sort(key=lambda mk: mk["offset_ql"])
    return anchored
