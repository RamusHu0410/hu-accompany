"""Phase 1 - Document Preparation.

Loads the PDF, renders every page to a high-DPI image, corrects rotation,
finds the content margins, and splits each page into staff-system regions.

Nothing here interprets *what* is on the page (no note/clef/etc. detection -
that's Phase 2). This phase only prepares clean, well-understood page images
and geometry for later phases to work from.
"""

import json
import logging
from pathlib import Path

import cv2
import fitz
import numpy as np

from .exceptions import InvalidPDFError, RenderError
from .models.document import (
    DocumentMetadata,
    DocumentPreparation,
    PageError,
    PageInfo,
    StaffRegion,
)
from .models.objects import BoundingBox
from .utils.cache import file_content_hash, render_cache_dir

_NULL_LOGGER = logging.getLogger("pipeline.null")
_NULL_LOGGER.addHandler(logging.NullHandler())


def load_pdf(pdf_path: Path) -> fitz.Document:
    if not pdf_path.exists():
        raise InvalidPDFError(f"File does not exist: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # fitz raises its own exception types per-format
        raise InvalidPDFError(f"Could not open '{pdf_path}' as a PDF: {exc}") from exc
    if doc.page_count == 0:
        doc.close()
        raise InvalidPDFError(f"'{pdf_path}' has zero pages")
    return doc


def extract_metadata(doc: fitz.Document, pdf_path: Path) -> DocumentMetadata:
    meta = doc.metadata or {}
    return DocumentMetadata(
        source_path=str(pdf_path),
        page_count=doc.page_count,
        title=meta.get("title") or "",
        author=meta.get("author") or "",
        producer=meta.get("producer") or "",
    )


def render_page(
    doc: fitz.Document,
    page_index: int,
    dpi: int,
    out_dir: Path,
    logger: logging.Logger,
) -> tuple[Path, int, int]:
    """Render a single page to PNG, reusing a cached render if present."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page_{page_index + 1:03d}.png"

    if out_path.exists():
        logger.debug("page %d: render cache hit (%s)", page_index + 1, out_path)
        height, width = cv2.imread(str(out_path)).shape[:2]
        return out_path, width, height

    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
        pix.save(out_path)
    except Exception as exc:
        raise RenderError(f"Failed to render page {page_index + 1}: {exc}") from exc

    return out_path, pix.width, pix.height


def _ink_mask(gray: np.ndarray, threshold: int) -> np.ndarray:
    """Binary mask where True = ink (dark pixel)."""
    return gray < threshold


def detect_rotation(gray: np.ndarray) -> float:
    """Estimate page skew in degrees from the dominant near-horizontal line
    angle (staff lines run the full width of the page)."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_len = gray.shape[1] * 0.3
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 720, threshold=150, minLineLength=min_len, maxLineGap=10
    )
    if lines is None:
        return 0.0

    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        angle = np.degrees(np.arctan2(dy, dx))
        if abs(angle) <= 10:  # discard anything not roughly horizontal
            angles.append(angle)

    if not angles:
        return 0.0
    return float(np.median(angles))


def correct_skew(image: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 0.05:
        return image
    h, w = image.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
    )


def detect_content_bbox(mask: np.ndarray) -> BoundingBox:
    """Bounding box of all ink pixels - i.e. the page content area, excluding
    blank margins."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        h, w = mask.shape
        return BoundingBox(x=0, y=0, width=w, height=h)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return BoundingBox(x=x0, y=y0, width=x1 - x0 + 1, height=y1 - y0 + 1)


def detect_staff_regions(
    mask: np.ndarray, content_bbox: BoundingBox, config
) -> list[StaffRegion]:
    """Heuristic staff-system detection via horizontal ink-density projection.

    Staff lines span most of the page width, so rows with unusually high ink
    density are line candidates. Five line candidates with near-equal
    spacing form one staff. This is a geometric approximation, not full OMR -
    good enough to hand later phases a region to work within, with a
    confidence score reflecting how regular the line spacing was.
    """
    row_density = mask.sum(axis=1)
    line_threshold = content_bbox.width * 0.3

    candidate_rows = np.where(row_density > line_threshold)[0]
    if len(candidate_rows) == 0:
        return []

    # Merge consecutive candidate rows into single line centers.
    line_centers = []
    group = [candidate_rows[0]]
    for row in candidate_rows[1:]:
        if row - group[-1] <= 2:
            group.append(row)
        else:
            line_centers.append(float(np.mean(group)))
            group = [row]
    line_centers.append(float(np.mean(group)))

    regions = []
    i = 0
    while i + config.min_staff_line_count <= len(line_centers):
        window = line_centers[i : i + config.min_staff_line_count]
        gaps = np.diff(window)
        mean_gap = float(np.mean(gaps))
        if mean_gap <= 0:
            i += 1
            continue
        regularity = 1.0 - min(float(np.std(gaps) / mean_gap), 1.0)

        if regularity >= (1.0 - config.staff_line_spacing_tolerance):
            margin = mean_gap * 2.0
            y0 = max(int(window[0] - margin), 0)
            y1 = int(window[-1] + margin)
            regions.append(
                StaffRegion(
                    bbox=BoundingBox(
                        x=content_bbox.x,
                        y=y0,
                        width=content_bbox.width,
                        height=y1 - y0,
                    ),
                    line_spacing_px=mean_gap,
                    confidence=round(regularity, 4),
                )
            )
            i += config.min_staff_line_count
        else:
            i += 1

    return regions


def draw_debug_overlay(
    image: np.ndarray, content_bbox: BoundingBox, staff_regions: list[StaffRegion]
) -> np.ndarray:
    overlay = image.copy()
    b = content_bbox
    cv2.rectangle(overlay, (b.x, b.y), (b.x + b.width, b.y + b.height), (0, 0, 255), 4)
    for region in staff_regions:
        r = region.bbox
        cv2.rectangle(
            overlay, (r.x, r.y), (r.x + r.width, r.y + r.height), (0, 200, 0), 3
        )
    return overlay


def process_page(
    doc: fitz.Document,
    page_index: int,
    config,
    render_dir: Path,
    debug_dir: Path,
    logger: logging.Logger,
) -> PageInfo:
    render_path, width, height = render_page(
        doc, page_index, config.render_dpi, render_dir, logger
    )

    image = cv2.imread(str(render_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    rotation = detect_rotation(gray)
    if abs(rotation) >= 0.05:
        corrected = correct_skew(image, rotation)
        corrected_gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
        corrected_path = render_dir / f"page_{page_index + 1:03d}_corrected.png"
        cv2.imwrite(str(corrected_path), corrected)
    else:
        corrected = image
        corrected_gray = gray
        corrected_path = None

    mask = _ink_mask(corrected_gray, config.binarize_threshold)
    content_bbox = detect_content_bbox(mask)
    staff_regions = detect_staff_regions(mask, content_bbox, config)

    logger.debug(
        "page %d: rotation=%.3f deg, content_bbox=%s, %d staff regions found",
        page_index + 1,
        rotation,
        content_bbox.to_dict(),
        len(staff_regions),
    )

    debug_dir.mkdir(parents=True, exist_ok=True)
    overlay = draw_debug_overlay(corrected, content_bbox, staff_regions)
    overlay_path = debug_dir / f"page_{page_index + 1:03d}_overlay.png"
    cv2.imwrite(str(overlay_path), overlay)

    return PageInfo(
        page_number=page_index + 1,
        render_path=str(render_path),
        width=width,
        height=height,
        rotation_deg=rotation,
        corrected_render_path=str(corrected_path) if corrected_path else None,
        content_bbox=content_bbox,
        staff_regions=staff_regions,
    )


def prepare_document(
    pdf_path: Path, config, logger: logging.Logger = _NULL_LOGGER
) -> DocumentPreparation:
    doc = load_pdf(pdf_path)
    try:
        metadata = extract_metadata(doc, pdf_path)
        pdf_hash = file_content_hash(pdf_path)
        render_dir = render_cache_dir(config.cache_dir, pdf_hash, config.render_dpi)
        debug_dir = config.debug_dir / "phase1"

        pages: list[PageInfo] = []
        page_errors: list[PageError] = []

        for page_index in range(doc.page_count):
            try:
                page_info = process_page(
                    doc, page_index, config, render_dir, debug_dir, logger
                )
                pages.append(page_info)
            except Exception as exc:
                logger.error(
                    "page %d failed in phase1: %s", page_index + 1, exc, exc_info=True
                )
                page_errors.append(
                    PageError(page_number=page_index + 1, stage="phase1_prepare", message=str(exc))
                )

        report = {
            "metadata": vars(metadata),
            "pages": [
                {
                    "page_number": p.page_number,
                    "render_path": p.render_path,
                    "width": p.width,
                    "height": p.height,
                    "rotation_deg": p.rotation_deg,
                    "corrected_render_path": p.corrected_render_path,
                    "content_bbox": p.content_bbox.to_dict() if p.content_bbox else None,
                    "staff_regions": [
                        {
                            "bbox": s.bbox.to_dict(),
                            "line_spacing_px": s.line_spacing_px,
                            "confidence": s.confidence,
                        }
                        for s in p.staff_regions
                    ],
                }
                for p in pages
            ],
            "page_errors": [vars(e) for e in page_errors],
        }
        debug_dir.mkdir(parents=True, exist_ok=True)
        with open(debug_dir / "report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return DocumentPreparation(metadata=metadata, pages=pages, page_errors=page_errors)
    finally:
        doc.close()
