"""Phase 4 - Composer Marking Analysis.

OCRs each page for the text markings oemer's vision pipeline never looks for
at all (tempo words, dynamics, expressions, technique instructions, time
signature) and attaches them to `objects` as new "text"-kind MusicObjects.
Phase 5 is what turns these page/pixel-anchored candidates into
measure/beat-anchored markings (it has the note timeline to anchor against);
this phase only detects and classifies the text itself.

OCR runs on Phase 1's original high-DPI render, not oemer's own downsampled/
dewarped image, because text legibility matters more here than coordinate
convenience - the detected boxes are rescaled into oemer's coordinate space
(the space every other Phase 2 bbox already lives in, e.g. barlines, so
Phase 5 can compare positions without unit conversion) via the ratio between
Phase 1's render size and Phase 2's oemer image_size.

Classification is closed-vocabulary (an exact word/symbol lookup), not free
text recognition: pytesseract run over a whole music page inevitably
misreads noteheads/beams/slurs as stray characters, and open-ended text
interpretation would treat that noise as content. Matching only against the
specific tempo/dynamic/expression/technique vocabulary the terms actually
come from (also what the design doc's Stage 6 lists) means garbage tokens
essentially never accidentally collide with a real marking word.
"""

import logging
import re
from pathlib import Path

import cv2

from .models.objects import BoundingBox, ConfidenceRecord, MusicObject

TEMPO_WORDS = {
    "larghissimo": 24, "grave": 35, "largo": 45, "lento": 50, "larghetto": 55,
    "adagio": 65, "adagietto": 70, "andante": 88, "andantino": 92,
    "moderato": 108, "allegretto": 112, "allegro": 132, "vivace": 160,
    "vivo": 160, "presto": 184, "prestissimo": 200,
}

DYNAMIC_WORDS = {
    "ppp": 0.05, "pp": 0.15, "p": 0.25, "mp": 0.40, "mf": 0.60,
    "f": 0.75, "ff": 0.88, "fff": 0.95, "fp": 0.60, "sfz": 0.85,
}

EXPRESSION_WORDS = {
    "dolce", "cantabile", "espressivo", "sempre", "rit.", "rit", "ritenuto",
    "accel.", "accel", "accelerando", "a tempo", "atempo", "legato",
    "staccato", "cresc.", "cresc", "crescendo", "dim.", "dim", "diminuendo",
    "poco", "molto", "meno", "piu", "più", "subito",
}

TECHNIQUE_WORDS = {
    "ped.": "pedal_down", "ped": "pedal_down", "una corda": "una_corda",
    "tre corde": "tre_corde", "sim.": "simile", "simile": "simile",
}

_TIME_SIG_RE = re.compile(r"^([2-9]|1[0-9])\s*/\s*([2-9]|1[0-9])$")
_BARE_DIGIT_RE = re.compile(r"^\d{1,2}$")

_OCR_CONFIDENCE_REASON = "pytesseract per-word confidence, scaled to 0-1"


def _classify_token(text: str) -> "tuple[str, object] | None":
    """Returns (marking_type, value) if `text` matches the closed vocabulary,
    else None. Checked in order of specificity so e.g. "p" (dynamic) isn't
    shadowed by a longer expression match."""
    lower = text.strip().lower().rstrip(".,;:")

    m = _TIME_SIG_RE.match(text.strip())
    if m:
        return "time_signature", f"{m.group(1)}/{m.group(2)}"

    if lower in DYNAMIC_WORDS:
        return "dynamic", DYNAMIC_WORDS[lower]

    if lower in TEMPO_WORDS:
        return "tempo", TEMPO_WORDS[lower]

    if lower in TECHNIQUE_WORDS:
        return "technique", TECHNIQUE_WORDS[lower]

    if lower in EXPRESSION_WORDS:
        return "expression", lower

    if _BARE_DIGIT_RE.match(text.strip()):
        # Ambiguous on its own - could be a tuplet number, a fingering, or a
        # rehearsal mark. Phase 6 disambiguates using position/context.
        return "digit", int(text.strip())

    return None


def _ocr_words(image_path: str) -> list:
    """Runs pytesseract on a page image, returns [(text, x, y, w, h, conf), ...]
    in that image's own pixel space. Returns [] if pytesseract isn't usable -
    markings are a best-effort enhancement, not required for notes.json."""
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return []

    image = cv2.imread(image_path)
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    data = pytesseract.image_to_data(gray, config="--psm 11 --oem 3", output_type=Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = int(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1
        if conf < 0:
            continue
        words.append((
            text,
            int(data["left"][i]), int(data["top"][i]),
            int(data["width"][i]), int(data["height"][i]),
            conf,
        ))
    return words


def analyze_markings(objects: list, prep, config, logger: logging.Logger) -> list:
    page_info_by_number = {p.page_number: p for p in prep.pages}
    total_found = 0

    for page_det in objects:
        if page_det.error:
            continue
        page_info = page_info_by_number.get(page_det.page)
        if page_info is None or page_det.image_size is None:
            continue

        render_path = page_info.corrected_render_path or page_info.render_path
        oemer_w, oemer_h = page_det.image_size
        sx = oemer_w / page_info.width
        sy = oemer_h / page_info.height

        words = _ocr_words(render_path)
        next_obj_id = max((o.id for o in page_det.objects), default=0) + 1

        for text, x, y, w, h, conf in words:
            classified = _classify_token(text)
            if classified is None:
                continue
            marking_type, value = classified

            bbox = BoundingBox(
                x=int(x * sx), y=int(y * sy),
                width=max(int(w * sx), 1), height=max(int(h * sy), 1),
            )
            page_det.objects.append(MusicObject(
                id=next_obj_id,
                page=page_det.page,
                bbox=bbox,
                ocr_text=text,
                primary_label=f"marking:{marking_type}",
                confidence_history=[ConfidenceRecord(
                    stage="phase4_markings", value=round(conf / 100.0, 3), reason=_OCR_CONFIDENCE_REASON,
                )],
                attributes={"kind": "text", "marking_type": marking_type, "value": value},
            ))
            next_obj_id += 1
            total_found += 1

    logger.info("phase4_markings: %d marking candidates found via OCR", total_found)
    return objects
