"""Phase 2 - Vision Detection.

Wraps oemer's detection stages (deep-learning staff/notehead/symbol
detection) per rendered page and converts its output into MusicObject
records: notes, rests, clefs, and accidentals, each with a bbox and the
label oemer assigned. Barlines are kept separately on PageDetection since
they're layout, not a musical object to classify.

This calls oemer's extraction stages directly instead of its top-level
extract() (inference/dewarp/staff/notehead/group/symbol/rhythm), matching
oemer.ete.extract() so results line up with what oemer itself would produce.

It then also drives oemer's own MusicXMLBuilder (build() + to_musicxml())
per page, reading from the same oemer.layers globals the extraction calls
above populated - this is exactly what oemer.ete.extract() does next, we're
just capturing the MusicXML instead of only writing it to disk. That
document is oemer's own pitch/rhythm/voice/chord reasoning (computed inside
build(), not before it) - Phase 5 parses it with music21 rather than
re-deriving pitch/duration/voices from raw MusicObject data. build() only
hard-asserts for 3+ simultaneous staves in one system (track_nums not in
{1, 2}); mono and grand-staff parts hit an early-return and build fine. If
it does fail for some page (e.g. a genuine 3+-staff system, or a decoding
edge case), that failure is caught and logged per-page - the page's
MusicObject detections (still useful for markings/validation) are kept
either way, just without a MusicXML for Phase 5 to stitch in for that page.

oemer's model directly assigns a label to each detection (there's no raw
"unclassified blob" stage to hand to Phase 3), and it exposes no per-object
confidence score - so `final_confidence()` is a fixed placeholder here, not a
measured probability. Real classification-with-alternatives (Phase 3) and
confidence work has to layer on top of oemer's output, not replace it.

Results are cached per page (keyed by the source image's content hash) under
output/cache/oemer/, since one page can take several minutes of CPU on a
laptop - re-running the pipeline on an unchanged render should not redo it.
"""

import concurrent.futures
import itertools
import json
import logging
import os
import urllib.request
from pathlib import Path

import numpy as np

# oemer 0.1.5 uses np.int / np.float / np.bool, removed in NumPy 1.24+.
# Must patch before oemer (or anything it imports) is imported anywhere.
for _alias, _builtin in (("int", int), ("float", float), ("bool", bool), ("complex", complex)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _builtin)

import cv2  # noqa: E402  (must follow the numpy patch above)
import oemer.bbox as _oemer_bbox  # noqa: E402
import oemer.staffline_extraction as _oemer_staffline  # noqa: E402
import oemer.symbol_extraction as _oemer_symbol  # noqa: E402
from oemer import layers as oemer_layers  # noqa: E402
from oemer.build_system import MusicXMLBuilder  # noqa: E402
from oemer.dewarp import dewarp, estimate_coords  # noqa: E402
from oemer.ete import CHECKPOINTS_URL, MODULE_PATH, clear_data, register_note_id  # noqa: E402
from oemer.inference import inference as _oemer_inference  # noqa: E402
from oemer.note_group_extraction import extract as _group_extract  # noqa: E402
from oemer.notehead_extraction import extract as _note_extract  # noqa: E402
from oemer.rhythm_extraction import extract as _rhythm_extract  # noqa: E402
from oemer.staffline_extraction import extract as _staff_extract  # noqa: E402
from oemer.symbol_extraction import extract as _symbol_extract  # noqa: E402

from .exceptions import DetectionError
from .models.document import DocumentPreparation
from .models.objects import BoundingBox, ConfidenceRecord, MusicObject, PageDetection
from .utils.cache import detection_cache_dir, file_content_hash
from .utils.logging_setup import configure_logging


def _find_lines_fixed(data: np.ndarray, min_len: int = 10, max_gap: int = 20) -> list:
    """Drop-in replacement for oemer.bbox.find_lines.

    OpenCV 5.0 changed cv2.HoughLinesP's output from shape (N, 1, 4) to
    (N, 4). oemer 0.1.5's original find_lines still unwraps the old extra
    dimension (`line = line[0]`), which under the new shape indexes into a
    single coordinate instead of a 4-tuple and crashes with
    "IndexError: invalid index to scalar variable". reshape(-1, 4) accepts
    either shape, so this works against old and new OpenCV alike.
    """
    lines = cv2.HoughLinesP(data.astype(np.uint8), 1, np.pi / 180, 50, None, min_len, max_gap)
    if lines is None:
        return []
    new_line = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        top_x, bt_x = (x1, x2) if x1 < x2 else (x2, x1)
        top_y, bt_y = (y1, y2) if y1 < y2 else (y2, y1)
        new_line.append((top_x, top_y, bt_x, bt_y))
    return new_line


_oemer_bbox.find_lines = _find_lines_fixed
_oemer_staffline.find_lines = _find_lines_fixed
_oemer_symbol.find_lines = _find_lines_fixed

_CONFIDENCE_REASON = (
    "oemer exposes no per-object confidence score; this is a fixed "
    "placeholder marking 'oemer accepted this detection', not a measured "
    "probability"
)


def _ensure_checkpoints(logger: logging.Logger) -> None:
    """Download oemer's ONNX weights on first use (~100 MB, cached in the
    package's own directory so this only happens once per environment)."""
    unet_onnx = os.path.join(MODULE_PATH, "checkpoints", "unet_big", "model.onnx")
    if os.path.exists(unet_onnx):
        return
    logger.info("phase2_detect: downloading oemer ONNX checkpoints (~100MB, one-time)")
    for title, url in CHECKPOINTS_URL.items():
        if not title.endswith(".onnx"):
            continue
        sub_dir = "unet_big" if title.startswith("1st") else "seg_net"
        dest_dir = os.path.join(MODULE_PATH, "checkpoints", sub_dir)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, title.split("_", 1)[1])
        if not os.path.exists(dest):
            urllib.request.urlretrieve(url, dest)
    logger.info("phase2_detect: checkpoints ready")


def _generate_pred(img_path: str, unet_step_size: int, seg_step_size: int) -> tuple:
    """Equivalent to oemer.ete.generate_pred, but with the sliding-window
    step size exposed instead of hardcoded to 128.

    oemer's two models scan the page in overlapping windows and average the
    overlaps (unet_big: 256x256 window, seg_net: 288x288). The hardcoded
    step of 128 makes every window overlap its neighbors by ~50%, i.e. it
    runs each model on ~4-5x more windows than the page's area requires.
    Setting step_size to each model's own window size drops overlap to zero
    - full coverage, no gaps - for a ~4-5x speedup with no resolution loss;
    the only thing lost is the cross-window averaging at tile boundaries.
    """
    staff_symbols_map, _ = _oemer_inference(
        os.path.join(MODULE_PATH, "checkpoints/unet_big"),
        img_path,
        step_size=unet_step_size,
    )
    staff = np.where(staff_symbols_map == 1, 1, 0)
    symbols = np.where(staff_symbols_map == 2, 1, 0)

    sep, _ = _oemer_inference(
        os.path.join(MODULE_PATH, "checkpoints/seg_net"),
        img_path,
        manual_th=None,
        step_size=seg_step_size,
    )
    stems_rests = np.where(sep == 1, 1, 0)
    notehead = np.where(sep == 2, 1, 0)
    clefs_keys = np.where(sep == 3, 1, 0)

    return staff, symbols, stems_rests, notehead, clefs_keys


def _run_oemer(img_path: Path, work_dir: Path, config, logger: logging.Logger) -> dict:
    """Run oemer's detection stages on one page image, returning every layer
    this phase needs, then build oemer's own MusicXML from those layers.
    This matches oemer.ete.extract()'s call sequence exactly - detection
    calls followed by MusicXMLBuilder. Must not run concurrently with
    another call - oemer keeps its results in process-wide global state
    (oemer.layers).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    clear_data()
    try:
        staff, symbols, stems_rests, notehead, clefs_keys = _generate_pred(
            str(img_path), config.oemer_unet_step_size, config.oemer_seg_step_size
        )

        image = cv2.imread(str(img_path))
        image = cv2.resize(image, (staff.shape[1], staff.shape[0]))

        coords_x, coords_y = estimate_coords(staff)
        staff = dewarp(staff, coords_x, coords_y)
        symbols = dewarp(symbols, coords_x, coords_y)
        stems_rests = dewarp(stems_rests, coords_x, coords_y)
        clefs_keys = dewarp(clefs_keys, coords_x, coords_y)
        notehead = dewarp(notehead, coords_x, coords_y)
        for i in range(image.shape[2]):
            image[..., i] = dewarp(image[..., i], coords_x, coords_y)

        symbols = symbols + clefs_keys + stems_rests
        symbols[symbols > 1] = 1
        oemer_layers.register_layer("stems_rests_pred", stems_rests)
        oemer_layers.register_layer("clefs_keys_pred", clefs_keys)
        oemer_layers.register_layer("notehead_pred", notehead)
        oemer_layers.register_layer("symbols_pred", symbols)
        oemer_layers.register_layer("staff_pred", staff)
        oemer_layers.register_layer("original_image", image)

        staffs, zones = _staff_extract()
        oemer_layers.register_layer("staffs", staffs)
        oemer_layers.register_layer("zones", zones)

        notes = _note_extract()
        oemer_layers.register_layer("notes", np.array(notes))
        oemer_layers.register_layer("note_id", np.zeros(symbols.shape, dtype=int) - 1)
        register_note_id()

        groups, group_map = _group_extract()
        oemer_layers.register_layer("note_groups", np.array(groups))
        oemer_layers.register_layer("group_map", group_map)

        barlines, clefs, sfns, rests = _symbol_extract()
        oemer_layers.register_layer("barlines", np.array(barlines))
        oemer_layers.register_layer("clefs", np.array(clefs))
        oemer_layers.register_layer("sfns", np.array(sfns))
        oemer_layers.register_layer("rests", np.array(rests))

        _rhythm_extract()
    except Exception as exc:
        raise DetectionError(f"oemer failed on '{img_path}': {exc}") from exc

    original_image = oemer_layers.get_layer("original_image")
    image_path = work_dir / "oemer_image.png"
    cv2.imwrite(str(image_path), original_image)

    musicxml_path = None
    try:
        builder = MusicXMLBuilder(title=Path(img_path).stem)
        builder.build()
        xml = builder.to_musicxml()
        musicxml_path = work_dir / "page.musicxml"
        with open(musicxml_path, "wb") as f:
            f.write(xml)
    except Exception as exc:
        logger.warning("phase2_detect: MusicXML build failed for '%s': %s", img_path, exc)
        musicxml_path = None

    return {
        "image_path": str(image_path),
        "image_size": (int(original_image.shape[1]), int(original_image.shape[0])),
        "notes": list(oemer_layers.get_layer("notes")),
        "barlines": list(oemer_layers.get_layer("barlines")),
        "clefs": list(oemer_layers.get_layer("clefs")),
        "sfns": list(oemer_layers.get_layer("sfns")),
        "rests": list(oemer_layers.get_layer("rests")),
        "musicxml_path": str(musicxml_path) if musicxml_path else None,
    }


def _bbox(xyxy) -> BoundingBox:
    x1, y1, x2, y2 = (int(v) for v in xyxy)
    return BoundingBox(x=x1, y=y1, width=max(x2 - x1, 0), height=max(y2 - y1, 0))


def _music_object(obj_id: int, page: int, kind: str, bbox_xyxy, label_name, staff=None, attributes=None) -> MusicObject:
    return MusicObject(
        id=obj_id,
        page=page,
        bbox=_bbox(bbox_xyxy),
        staff=staff,
        primary_label=label_name,
        confidence_history=[ConfidenceRecord(stage="phase2_detect", value=1.0, reason=_CONFIDENCE_REASON)],
        attributes={"kind": kind, **(attributes or {})},
    )


def _build_objects(page: int, raw: dict, next_id) -> list:
    objects = []

    for nh in raw["notes"]:
        if nh is None or getattr(nh, "invalid", True) or nh.label is None:
            continue
        accidental = nh.sfn.name if getattr(nh, "sfn", None) is not None else None
        objects.append(_music_object(
            next_id(), page, "note", nh.bbox, nh.label.name, staff=nh.track,
            attributes={
                "group": nh.group,
                "stem_up": nh.stem_up,
                "has_dot": nh.has_dot,
                "accidental": accidental,
                "staff_line_pos": nh.staff_line_pos,
            },
        ))

    for rest in raw["rests"]:
        if rest is None or rest.label is None:
            continue
        objects.append(_music_object(
            next_id(), page, "rest", rest.bbox, rest.label.name, staff=rest.track,
            attributes={"group": rest.group, "has_dot": rest.has_dot},
        ))

    for clef in raw["clefs"]:
        if clef is None or clef.label is None:
            continue
        objects.append(_music_object(
            next_id(), page, "clef", clef.bbox, clef.label.name, staff=clef.track,
            attributes={"group": clef.group},
        ))

    for sfn in raw["sfns"]:
        if sfn is None or sfn.label is None:
            continue
        objects.append(_music_object(
            next_id(), page, "accidental", sfn.bbox, sfn.label.name, staff=sfn.track,
            attributes={"group": sfn.group, "is_key": sfn.is_key, "note_id": sfn.note_id},
        ))

    return objects


def _json_default(o):
    """oemer's objects carry numpy scalar types (e.g. track/group as
    np.int64) which json can't serialize natively."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _save_cache(cache_dir: Path, objects: list, raw: dict) -> None:
    payload = {
        "image_path": raw["image_path"],
        "image_size": list(raw["image_size"]),
        "musicxml_path": raw.get("musicxml_path"),
        "barlines": [list(b.bbox) for b in raw["barlines"]],
        "objects": [
            {
                "id": o.id,
                "page": o.page,
                "bbox": o.bbox.to_dict(),
                "staff": o.staff,
                "primary_label": o.primary_label,
                "attributes": o.attributes,
                "confidence": [{"stage": c.stage, "value": c.value, "reason": c.reason} for c in o.confidence_history],
            }
            for o in objects
        ],
    }
    with open(cache_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)


def _load_cache(cache_dir: Path) -> tuple:
    with open(cache_dir / "result.json", "r", encoding="utf-8") as f:
        payload = json.load(f)

    objects = []
    for o in payload["objects"]:
        b = o["bbox"]
        objects.append(MusicObject(
            id=o["id"],
            page=o["page"],
            bbox=BoundingBox(x=b["x"], y=b["y"], width=b["width"], height=b["height"]),
            staff=o["staff"],
            primary_label=o["primary_label"],
            attributes=o["attributes"],
            confidence_history=[ConfidenceRecord(**c) for c in o["confidence"]],
        ))

    barlines = [BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1) for x1, y1, x2, y2 in payload["barlines"]]
    return objects, barlines, payload["image_path"], tuple(payload["image_size"]), payload.get("musicxml_path")


def draw_debug_overlay(image: np.ndarray, objects: list) -> np.ndarray:
    overlay = image.copy()
    colors = {
        "note": (0, 200, 50),
        "rest": (0, 165, 255),
        "clef": (255, 0, 180),
        "accidental": (255, 180, 0),
    }
    for obj in objects:
        color = colors.get(obj.attributes.get("kind"), (150, 150, 150))
        b = obj.bbox
        cv2.rectangle(overlay, (b.x, b.y), (b.x + b.width, b.y + b.height), color, 2)
    return overlay


def process_page(
    page_number: int,
    image_path: Path,
    config,
    logger: logging.Logger,
) -> PageDetection:
    """Ids assigned here are only unique within this page - each page can run
    in its own worker process (see detect()), so document-wide uniqueness is
    established afterward by renumbering all pages' objects in page order."""
    next_id = itertools.count(1).__next__
    image_hash = file_content_hash(image_path)
    cache_dir = detection_cache_dir(config.cache_dir, image_hash)

    if (cache_dir / "result.json").exists():
        logger.debug("page %d: oemer cache hit (%s)", page_number, cache_dir)
        objects, barlines, oemer_image_path, image_size, musicxml_path = _load_cache(cache_dir)
        for obj in objects:
            obj.id = next_id()
    else:
        raw = _run_oemer(image_path, cache_dir, config, logger)
        objects = _build_objects(page_number, raw, next_id)
        _save_cache(cache_dir, objects, raw)
        barlines = [_bbox(b.bbox) for b in raw["barlines"]]
        oemer_image_path, image_size = raw["image_path"], raw["image_size"]
        musicxml_path = raw.get("musicxml_path")

    debug_dir = config.debug_dir / "phase2"
    debug_dir.mkdir(parents=True, exist_ok=True)
    oemer_image = cv2.imread(oemer_image_path)
    if oemer_image is not None:
        overlay = draw_debug_overlay(oemer_image, objects)
        cv2.imwrite(str(debug_dir / f"page_{page_number:03d}_overlay.png"), overlay)

    logger.debug(
        "page %d: %d objects detected (%d notes, %d rests, %d clefs, %d accidentals)",
        page_number,
        len(objects),
        sum(1 for o in objects if o.attributes.get("kind") == "note"),
        sum(1 for o in objects if o.attributes.get("kind") == "rest"),
        sum(1 for o in objects if o.attributes.get("kind") == "clef"),
        sum(1 for o in objects if o.attributes.get("kind") == "accidental"),
    )

    return PageDetection(
        page=page_number,
        image_path=oemer_image_path,
        image_size=image_size,
        objects=objects,
        barlines=barlines,
        musicxml_path=musicxml_path,
    )


def _process_page_worker(args: tuple) -> PageDetection:
    """Module-level (picklable) wrapper so ProcessPoolExecutor can run this
    per page. Each worker process gets its own log file - a shared Logger
    object/file handle can't cross the process boundary - and, more
    importantly, its own process-wide oemer.layers state, which is exactly
    why pages run in separate processes rather than threads (see
    _run_oemer's docstring: oemer's results live in global state and one
    call must not run concurrently with another)."""
    page_number, image_path_str, config, log_dir_str, run_id = args
    worker_logger = configure_logging(Path(log_dir_str), f"{run_id}_p{page_number:03d}")
    return process_page(page_number, Path(image_path_str), config, worker_logger)


def detect(prep: DocumentPreparation, config, logger: logging.Logger) -> list:
    _ensure_checkpoints(logger)

    pages = prep.pages
    if not pages:
        return []

    run_id = logger.name.rsplit(".", 1)[-1]
    tasks = [
        (p.page_number, str(Path(p.corrected_render_path or p.render_path)), config, str(config.logs_dir), run_id)
        for p in pages
    ]
    max_workers = max(1, min(getattr(config, "oemer_max_workers", 1), len(tasks)))

    results_by_page = {}
    if max_workers <= 1:
        for task in tasks:
            page_number = task[0]
            try:
                results_by_page[page_number] = _process_page_worker(task)
            except Exception as exc:
                logger.error("page %d failed in phase2: %s", page_number, exc, exc_info=True)
                results_by_page[page_number] = PageDetection(page=page_number, error=str(exc))
    else:
        logger.info("phase2_detect: processing %d pages across %d worker processes", len(tasks), max_workers)
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {executor.submit(_process_page_worker, task): task[0] for task in tasks}
            for future in concurrent.futures.as_completed(future_to_page):
                page_number = future_to_page[future]
                try:
                    results_by_page[page_number] = future.result()
                except Exception as exc:
                    logger.error("page %d failed in phase2: %s", page_number, exc, exc_info=True)
                    results_by_page[page_number] = PageDetection(page=page_number, error=str(exc))

    results = [results_by_page[p.page_number] for p in pages]

    # Renumber ids document-wide in page order - worker processes each only
    # guaranteed uniqueness within their own page (see process_page).
    next_id = itertools.count(1)
    for page_det in results:
        for obj in page_det.objects:
            obj.id = next(next_id)

    total_objects = sum(len(r.objects) for r in results)
    logger.info("phase2_detect: %d objects detected across %d pages", total_objects, len(results))
    return results
