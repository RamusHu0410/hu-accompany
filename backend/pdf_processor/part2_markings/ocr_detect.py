"""
OCR a page image for the text markings oemer's vision pipeline never looks
for at all (tempo words, dynamics, expressions, technique instructions, time
signature), classifying each recognized word against the closed vocabulary
in `vocabulary.py`.

Ported from an earlier prototype's `phase4_markings.py`. Works on whatever
page image it's given (see part2_markings/detect.py for how callers rescale
the returned pixel-space boxes into oemer's coordinate space).

A single whole-page tesseract pass misses many small italic dynamics/
expression marks entirely -- not a low-confidence read, no read whatsoever.
tesseract's page-segmentation step, run once over a whole page of dense
engraved notation, sometimes fails to isolate these as text regions at all
(confirmed by dumping every raw token tesseract produced on a real page:
several marks never appeared in the output under any confidence). Cropping
into overlapping horizontal strips and upscaling each one before OCR
recovers some of these by giving tesseract's segmenter a much simpler,
mostly-blank region to work with instead of a whole page of dense ink --
but measured against the same page, the whole-page pass and the strip
passes each catch real marks the other one misses, neither is a superset
of the other. So `detect()` runs both and merges the results rather than
picking one strategy. This is still not complete recall (measured on a
real, marking-dense page: some marks -- e.g. "sf", a second "cresc."
instance a few measures later, an "accel" -- were caught by neither pass
in a given run) and it's noticeably slower than a single pass (several
seconds per page instead of ~1). A fundamentally different approach (e.g.
a music-notation-specific text detector, or an ensemble with a second OCR
engine) would be needed to do meaningfully better than this.
"""

import cv2

from .vocabulary import classify_token

STRIP_HEIGHT = 240  # px, in the source image's own resolution
STRIP_STEP = 120  # < STRIP_HEIGHT so consecutive strips overlap -- a mark
# sitting across a strip boundary in one pass still lands fully inside the
# next one, instead of being clipped in half in both.
UPSCALE = 2  # tesseract reads small italic engraving text far more
# reliably enlarged; see module docstring.

# pytesseract per-word confidence, 0-1, thresholded separately by marking
# type. Whole-page OCR on dense engravings misreads note stems/beams/blank
# staff gaps as stray 1-2 character tokens ("f", "F", "ff") constantly --
# exactly the short tokens the dynamics vocabulary is built from -- so a
# low-confidence dynamic is almost always noise, not a "maybe useful" middle
# ground. Measured on a real test page: every such false positive scored
# <= 0.43. Longer, more distinctive words (tempo/expression/technique, e.g.
# "scherzando", "cresc.") essentially never arise by coincidence from
# misread notation ink, so they get a much lower floor -- otherwise small
# italic markings (measured: a real "cresc." scored only 0.49) get dropped
# along with the noise.
MIN_CONFIDENCE_DYNAMIC = 0.6
MIN_CONFIDENCE_OTHER = 0.3

# Dedup bucket size (px, pre-upscale) for collapsing the same word read
# twice from two overlapping strips -- rounds each detection's position
# down to a coarse grid so near-identical boxes land in the same bucket
# regardless of the few-pixel jitter between strips.
_DEDUP_GRID = 20


def _ocr_region(gray_region, y_offset: int, scale: int) -> list:
    import pytesseract
    from pytesseract import Output

    im = cv2.resize(gray_region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1 else gray_region
    data = pytesseract.image_to_data(im, config="--psm 11 --oem 3", output_type=Output.DICT)

    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = int(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1
        if conf < 0:
            continue

        x = data["left"][i] / scale
        y = y_offset + data["top"][i] / scale
        w = data["width"][i] / scale
        h = data["height"][i] / scale
        words.append((text, conf, x, y, w, h))

    return words


def _dedupe(words: list) -> list:
    """Overlapping strips read the same word twice near their shared
    border; keep only the higher-confidence read of each near-duplicate."""
    best = {}
    for text, conf, x, y, w, h in words:
        key = (text.lower(), round(x / _DEDUP_GRID), round(y / _DEDUP_GRID))
        if key not in best or conf > best[key][1]:
            best[key] = (text, conf, x, y, w, h)
    return list(best.values())


def detect(image_path: str) -> list:
    """
    Returns [{"text", "type", "value", "bbox": (x1, y1, x2, y2), "confidence"}, ...]
    in `image_path`'s own pixel space. Returns [] if pytesseract isn't
    usable -- markings are a best-effort enhancement, not required for
    notes.json.
    """
    try:
        import pytesseract  # noqa: F401 -- import-checked here, used in _ocr_strip
    except ImportError:
        return []

    image = cv2.imread(image_path)
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height = gray.shape[0]

    # A plain whole-page pass and the tiled, upscaled-strip passes below
    # each surface a different subset of the page's marks -- neither is a
    # superset of the other (measured: the whole-page pass reliably reads
    # some marks a good strip split misses, and vice versa) -- so both run
    # and their results get merged, rather than picking just one strategy.
    raw_words = list(_ocr_region(gray, 0, scale=1))
    y = 0
    while True:
        y2 = min(y + STRIP_HEIGHT, height)
        raw_words.extend(_ocr_region(gray[y:y2, :], y, scale=UPSCALE))
        if y2 >= height:
            break
        y += STRIP_STEP

    classified_markings = []
    for text, conf, x, y, w, h in _dedupe(raw_words):
        classified = classify_token(text)
        if classified is None:
            continue
        marking_type, value = classified

        min_confidence = MIN_CONFIDENCE_DYNAMIC if marking_type == "dynamic" else MIN_CONFIDENCE_OTHER
        if conf / 100.0 < min_confidence:
            continue

        x1, y1 = round(x), round(y)
        classified_markings.append({
            "text": text,
            "type": marking_type,
            "value": value,
            "bbox": (x1, y1, round(x1 + w), round(y1 + h)),
            "confidence": round(conf / 100.0, 3),
        })

    # Two overlapping strips can OCR the same printed mark slightly
    # differently (e.g. "primo" vs "primo)", one keeping a stray trailing
    # paren) -- different raw text, so _dedupe above didn't catch it, but
    # they classify to the same (type, value) at nearly the same position.
    # Dedupe again post-classification for exactly that case.
    final = {}
    for mk in classified_markings:
        x1, y1, _, _ = mk["bbox"]
        key = (mk["type"], mk["value"], round(x1 / _DEDUP_GRID), round(y1 / _DEDUP_GRID))
        if key not in final or mk["confidence"] > final[key]["confidence"]:
            final[key] = mk

    return list(final.values())
