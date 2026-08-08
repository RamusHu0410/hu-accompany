"""Phase 5 - Music Notation Reasoning.

Builds the piece's continuous note/marking structure from oemer's per-page
MusicXML (parsed with music21) plus Phase 4's OCR marking candidates.

oemer's own MusicXMLBuilder already resolves pitch (clef + staff position +
accidental + key), rhythm (notehead/stem/beam/flag/dot), voice separation,
and chord grouping - see phase2_detect.py's module docstring for why this
phase parses that MusicXML instead of re-deriving any of it from raw
MusicObject data. What's left for this phase, which oemer's per-page,
context-free MusicXML cannot do on its own:

  1. Stitch pages into one continuous piece. Each page's MusicXML is a
     self-contained document (its own measure 1, its own offset 0) - this
     phase accumulates running measure-number and quarter-length offsets so
     the whole piece has one measure sequence and one timeline.
  2. Infer a time signature. oemer never emits <time> (no dedicated
     time-signature-glyph detection) - Phase 4's OCR gets first try at
     reading the printed signature; where that's missing, this phase falls
     back to the statistical mode of measure lengths (most measures should
     match the true signature; outliers usually mean a rhythm-detection
     error, not a real signature change - the two are naturally very
     different populations, so mode over median/mean is deliberate here).
  3. Anchor Phase 4's OCR marking candidates - which only know their page
     and pixel position - to a (measure, beat) in the stitched timeline.
     Positions are compared using barline pixel x-coordinates, which are
     already in the same coordinate space Phase 4 was told to OCR in
     (oemer's resized/dewarped page image, not Phase 1's original render -
     see phase4_markings.py), so no cross-coordinate-space mapping is
     needed. Beat is linear interpolation between the two enclosing
     barlines, i.e. proportional-to-x-position, not a measured time value -
     engraving spaces notes roughly proportionally to their duration, but
     this is an approximation, not an exact readout.

oemer does not detect ties, slurs, hairpins, or tuplet brackets (nothing in
its label taxonomy covers them - see phase2_detect.py). Each written note
here is treated as sounding for exactly its own notated duration; a tied
note will show up as two separate short notes rather than one long one.
That's a known accuracy gap in this pipeline, not an oversight - closing it
would need a dedicated curve/bracket detector this codebase doesn't have.
"""

import logging
from collections import Counter
from pathlib import Path

import music21


def _parse_page_score(page_det, logger: logging.Logger):
    if not getattr(page_det, "musicxml_path", None):
        return None
    try:
        return music21.converter.parse(page_det.musicxml_path)
    except Exception as exc:
        logger.warning("phase5_reasoning: failed to parse musicxml for page %d: %s", page_det.page, exc)
        return None


def _infer_time_signature(measure_durations_ql: list) -> tuple:
    """Mode of measure lengths, expressed as (numerator, denominator) assuming
    a quarter-note beat (denominator=4) - matches how oemer expresses duration
    internally, and is precise enough for the beat-total validation Phase 7
    does with this value. Defaults to 4/4 when nothing has been measured yet."""
    if not measure_durations_ql:
        return (4, 4)
    counts = Counter(round(d, 4) for d in measure_durations_ql)
    mode_ql = counts.most_common(1)[0][0]
    return (max(mode_ql, 1), 4)


def _extract_page_notes(page_det, score, measure_offset: int, time_offset_ql: float, logger: logging.Logger) -> tuple:
    """Flatten one page's music21 Score into note/rest dicts on the stitched
    timeline. Returns (notes, page_measure_count, page_duration_ql,
    measure_durations_ql) - the last two feed the next page's running offsets
    and the time-signature inference, respectively."""
    notes = []
    measure_durations_ql: dict = {}  # local measure number -> quarterLength, for mode inference
    page_max_measure = 0
    page_max_end_ql = 0.0

    for part_idx, part in enumerate(score.parts):
        for m in part.getElementsByClass("Measure"):
            measure_durations_ql[m.number] = float(m.barDuration.quarterLength)
            page_max_measure = max(page_max_measure, m.number)

            voices = m.voices if m.voices else [m]
            for voice_idx, v in enumerate(voices):
                for el in v.notesAndRests:
                    if el.isChord:
                        pitches_hz = [float(p.frequency) for p in el.pitches]
                    elif el.isNote:
                        pitches_hz = [float(el.pitch.frequency)]
                    else:  # rest
                        pitches_hz = []

                    duration_ql = float(el.duration.quarterLength)
                    offset_ql = time_offset_ql + float(m.offset) + float(el.offset)
                    page_max_end_ql = max(page_max_end_ql, float(m.offset) + float(el.offset) + duration_ql)

                    notes.append({
                        "page": page_det.page,
                        "part_index": part_idx,
                        "voice_index": voice_idx,
                        "measure": measure_offset + m.number,
                        "beat": float(el.offset),
                        "offset_ql": offset_ql,
                        "duration_ql": duration_ql,
                        "pitches_hz": pitches_hz,
                    })

    return notes, page_max_measure, page_max_end_ql, list(measure_durations_ql.values())


def _staff_y_ranges(page_det) -> dict:
    """Approximate y-range of each staff/track on a page from its own
    detected objects (no independent staff-region geometry survives past
    Phase 2 in oemer's coordinate space) - used to guess which staff a
    marking belongs to on multi-staff (e.g. piano) pages."""
    ranges: dict = {}
    for obj in page_det.objects:
        if obj.staff is None:
            continue
        y0, y1 = obj.bbox.y, obj.bbox.y + obj.bbox.height
        lo, hi = ranges.get(obj.staff, (y0, y1))
        ranges[obj.staff] = (min(lo, y0), max(hi, y1))
    return ranges


def _nearest_staff(y: float, staff_ranges: dict) -> "int | None":
    if not staff_ranges:
        return None
    return min(staff_ranges, key=lambda s: abs(y - sum(staff_ranges[s]) / 2))


def _anchor_markings(objects: list, measure_offsets: dict, time_offsets: dict, logger: logging.Logger) -> list:
    """Turn Phase 4's page/pixel-anchored marking candidates into
    measure/beat-anchored markings using barline positions on that page."""
    markings = []
    for page_det in objects:
        page_num = page_det.page
        barline_xs = sorted(b.x + b.width / 2 for b in page_det.barlines)
        staff_ranges = _staff_y_ranges(page_det)
        measure_offset = measure_offsets.get(page_num)
        if measure_offset is None:
            continue

        for obj in page_det.objects:
            if obj.attributes.get("kind") != "text":
                continue
            marking_type = obj.attributes.get("marking_type")
            if marking_type is None:
                continue

            cx = obj.bbox.x + obj.bbox.width / 2
            cy = obj.bbox.y + obj.bbox.height / 2

            if not barline_xs:
                local_measure, beat = 1, 0.0
            else:
                idx = 0
                while idx < len(barline_xs) and barline_xs[idx] <= cx:
                    idx += 1
                local_measure = idx + 1
                left = barline_xs[idx - 1] if idx > 0 else barline_xs[0] - 200
                right = barline_xs[idx] if idx < len(barline_xs) else left + 200
                span = max(right - left, 1.0)
                beat = max(0.0, min(1.0, (cx - left) / span)) * 4.0  # approx, see module docstring

            markings.append({
                "page": page_num,
                "measure": measure_offset + local_measure,
                "beat": round(beat, 3),
                "staff": _nearest_staff(cy, staff_ranges),
                "type": marking_type,
                "value": obj.attributes.get("value", obj.ocr_text),
                "text": obj.ocr_text,
                "confidence": obj.final_confidence(),
            })

    markings.sort(key=lambda mk: (mk["measure"], mk["beat"]))
    return markings


def reason(objects: list, config, logger: logging.Logger) -> dict:
    notes = []
    all_measure_durations_ql = []
    measure_offset_by_page = {}
    time_offset_by_page = {}
    page_errors = []

    measure_offset = 0
    time_offset_ql = 0.0

    for page_det in objects:
        if page_det.error:
            page_errors.append({"page": page_det.page, "stage": "phase2_detect", "message": page_det.error})
            continue

        measure_offset_by_page[page_det.page] = measure_offset
        time_offset_by_page[page_det.page] = time_offset_ql

        score = _parse_page_score(page_det, logger)
        if score is None:
            page_errors.append({
                "page": page_det.page, "stage": "phase5_reasoning",
                "message": "no MusicXML available for this page - contributes no notes",
            })
            continue

        page_notes, page_measures, page_end_ql, page_measure_durations = _extract_page_notes(
            page_det, score, measure_offset, time_offset_ql, logger
        )
        notes.extend(page_notes)
        all_measure_durations_ql.extend(page_measure_durations)
        measure_offset += page_measures
        time_offset_ql += page_end_ql

    notes.sort(key=lambda n: (n["offset_ql"], n["part_index"], n["voice_index"]))
    time_signature = _infer_time_signature(all_measure_durations_ql)
    markings = _anchor_markings(objects, measure_offset_by_page, time_offset_by_page, logger)

    logger.info(
        "phase5_reasoning: stitched %d notes/rests across %d measures (inferred time signature %d/%d), %d markings anchored",
        len(notes), measure_offset, time_signature[0], time_signature[1], len(markings),
    )

    return {
        "notes": notes,
        "markings": markings,
        "measure_count": measure_offset,
        "time_signature": time_signature,
        "page_errors": page_errors,
    }
