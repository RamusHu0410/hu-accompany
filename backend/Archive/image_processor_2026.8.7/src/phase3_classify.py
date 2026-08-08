"""Phase 3 - Object Classification.

Spec: assign each detected object a primary classification plus alternative
candidate labels with confidences (never a single forced interpretation when
uncertainty exists).

oemer's model assigns exactly one label per object with no alternative
hypotheses and no per-object confidence score (see phase2_detect.py's
module docstring) - there is no second opinion available to build real
alternatives from. What this phase actually does, honestly within that
limit: normalize oemer's internal enum names (e.g. NoteType.HALF_OR_WHOLE,
ClefType.TREBLE) into the design doc's symbol taxonomy (e.g.
"notehead_open", "clef_treble") and populate `candidate_labels` with that
one normalized label, since oemer's detector genuinely doesn't produce more
than one candidate per object to weigh.
"""

import logging

_NOTEHEAD_OPEN = {"WHOLE", "HALF", "HALF_OR_WHOLE"}

_CLEF_MAP = {
    "TREBLE": "clef_treble", "BASS": "clef_bass",
    "ALTO": "clef_alto", "TENOR": "clef_tenor",
}

_SFN_MAP = {
    "SHARP": "accidental_sharp", "FLAT": "accidental_flat",
    "NATURAL": "accidental_natural", "DOUBLE_SHARP": "accidental_double_sharp",
    "DOUBLE_FLAT": "accidental_double_flat",
}


def _normalize(obj) -> "str | None":
    kind = obj.attributes.get("kind")
    raw = obj.primary_label

    if kind == "note":
        return "notehead_open" if raw in _NOTEHEAD_OPEN else "notehead_filled"
    if kind == "rest":
        return f"rest_{raw.lower()}" if raw else None
    if kind == "clef":
        return _CLEF_MAP.get(raw)
    if kind == "accidental":
        return _SFN_MAP.get(raw)
    return None


def classify(objects: list, config, logger: logging.Logger) -> list:
    normalized_count = 0
    for page_det in objects:
        for obj in page_det.objects:
            if obj.attributes.get("kind") == "text":
                continue  # Phase 4's OCR markings - already fully classified there
            label = _normalize(obj)
            if label is None:
                continue
            obj.candidate_labels = [{"label": label, "confidence": obj.final_confidence()}]
            obj.attributes["oemer_raw_label"] = obj.primary_label
            obj.primary_label = label
            normalized_count += 1

    logger.info("phase3_classify: normalized %d object labels into the symbol taxonomy", normalized_count)
    return objects
