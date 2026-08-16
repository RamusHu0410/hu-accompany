"""
Part 2 entry point: detect composer markings (dynamics, tempo, expression,
technique, time signature text) on a page and anchor them onto the page's
music21 timeline.

Called from pdf_to_notes.process() -- not meant to be run standalone.
"""

from PIL import Image, ImageDraw

from . import ocr_detect
from .anchor import anchor as _anchor

MARKING_COLOR = (255, 215, 0)  # gold -- distinct from every color part1_notes'
                                # debug teaser already uses


def _rescale_bbox(bbox, sx, sy):
    x1, y1, x2, y2 = bbox
    return (round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy))


def _draw_overlay(working_png_path: str, markings: list, out_path: str) -> None:
    """Draws each marking's box + label onto a fresh copy of oemer's clean
    (unannotated) working image -- a dedicated debug image for part2, rather
    than adding onto part1_notes' already-busy notehead/clef/barline/
    accidental overlay, so marking boxes are easy to pick out by eye."""
    img = Image.open(working_png_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for mk in markings:
        x1, y1, x2, y2 = mk["bbox"]
        draw.rectangle((x1, y1, x2, y2), outline=MARKING_COLOR, width=2)
        draw.text((x2 + 2, y1), f"{mk['type']}:{mk['text']}", fill=MARKING_COLOR)
    img.save(out_path)


def detect_markings(ocr_png_path: str, oemer_image_size: tuple, barlines: list,
                     xml_path: str, working_png_path: str, debug_png_path: str) -> list:
    """
    Returns [{"offset_ql", "type", "value", "text", "confidence"}, ...],
    page-local (see anchor.anchor). `ocr_png_path` is the same page PNG
    already rendered for oemer (see pdf_to_notes.process()) -- oemer resizes
    it internally to its own working resolution, which is why bboxes still
    need rescaling into `oemer_image_size` below before anchoring.

    Always (re)writes `debug_png_path`, even with zero markings, so it's
    never a stale leftover from a previous run.
    """
    markings = ocr_detect.detect(ocr_png_path)

    ocr_w, ocr_h = Image.open(ocr_png_path).size
    oemer_w, oemer_h = oemer_image_size
    sx, sy = oemer_w / ocr_w, oemer_h / ocr_h
    rescaled = [{**mk, "bbox": _rescale_bbox(mk["bbox"], sx, sy)} for mk in markings]

    _draw_overlay(working_png_path, rescaled, debug_png_path)

    return _anchor(rescaled, barlines, xml_path)
