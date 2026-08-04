"""Phase 2 - Vision Detection.

Wraps oemer's detection stages (deep-learning staff/notehead/symbol
detection) per rendered page and converts its output into MusicObject
records: notes, rests, clefs, and accidentals, each with a bbox and the
label oemer assigned. Barlines are kept separately on PageDetection since
they're layout, not a musical object to classify.

This calls oemer's extraction stages directly instead of its top-level
extract() / MusicXMLBuilder: builder.build() hard-asserts exactly 2 staves
per system (`assert track_nums == 2`), i.e. it only supports piano grand
staff. Single-staff instrumental parts - like the violin part this was
built and tested against - hit that assertion and crash. Detection itself
(everything through rhythm_extract()) works for any staff count, so Phase 2
stops right before the MusicXML build step. Turning these raw objects into
pitch/duration/measures is Phase 5's job, done from MusicObject data rather
than from oemer's MusicXML.

oemer's model directly assigns a label to each detection (there's no raw
"unclassified blob" stage to hand to Phase 3), and it exposes no per-object
confidence score - so `final_confidence()` is a fixed placeholder here, not a
measured probability. Real classification-with-alternatives (Phase 3) and
confidence work has to layer on top of oemer's output, not replace it.

Results are cached per page (keyed by the source image's content hash) under
output/cache/oemer/, since one page can take several minutes of CPU on a
laptop - re-running the pipeline on an unchanged render should not redo it.
"""

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
from oemer.dewarp import dewarp, estimate_coords  # noqa: E402
from oemer.ete import CHECKPOINTS_URL, MODULE_PATH, clear_data, generate_pred, register_note_id  # noqa: E402
from oemer.note_group_extraction import extract as _group_extract  # noqa: E402
from oemer.notehead_extraction import extract as _note_extract  # noqa: E402
from oemer.rhythm_extraction import extract as _rhythm_extract  # noqa: E402
from oemer.staffline_extraction import extract as _staff_extract  # noqa: E402
from oemer.symbol_extraction import extract as _symbol_extract  # noqa: E402

from .exceptions import DetectionError
from .models.document import DocumentPreparation
from .models.objects import BoundingBox, ConfidenceRecord, MusicObject, PageDetection
from .utils.cache import detection_cache_dir, file_content_hash


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


def _run_oemer(img_path: Path, work_dir: Path) -> dict:
    """Run oemer's detection stages on one page image, returning every layer
    this phase needs. This is oemer.ete.extract() re-sequenced to stop
    before MusicXMLBuilder (see module docstring for why). Must not run
    concurrently with another call - oemer keeps its results in
    process-wide global state (oemer.layers).

    Object identity, not just values, matters here: builder.build() (not
    called here) is normally what allows attribute changes recorded on
    NoteHead/Sfn instances - like symbol_extraction pairing an accidental
    with a note - to be visible via oemer_layers.get_layer('notes') after
    the fact. All the pairing this phase relies on (note.sfn, note.group,
    note.track, ...) is already set by the extraction calls below, so
    skipping the builder does not lose it.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    clear_data()
    try:
        staff, symbols, stems_rests, notehead, clefs_keys = generate_pred(str(img_path))

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

    return {
        "image_path": str(image_path),
        "image_size": (int(original_image.shape[1]), int(original_image.shape[0])),
        "notes": list(oemer_layers.get_layer("notes")),
        "barlines": list(oemer_layers.get_layer("barlines")),
        "clefs": list(oemer_layers.get_layer("clefs")),
        "sfns": list(oemer_layers.get_layer("sfns")),
        "rests": list(oemer_layers.get_layer("rests")),
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
    return objects, barlines, payload["image_path"], tuple(payload["image_size"])


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
    next_id,
    logger: logging.Logger,
) -> PageDetection:
    image_hash = file_content_hash(image_path)
    cache_dir = detection_cache_dir(config.cache_dir, image_hash)

    if (cache_dir / "result.json").exists():
        logger.debug("page %d: oemer cache hit (%s)", page_number, cache_dir)
        objects, barlines, oemer_image_path, image_size = _load_cache(cache_dir)
        # Cached objects need their ids remapped into this run's id sequence
        # so ids stay unique document-wide even when only some pages hit cache.
        for obj in objects:
            obj.id = next_id()
    else:
        raw = _run_oemer(image_path, cache_dir)
        objects = _build_objects(page_number, raw, next_id)
        _save_cache(cache_dir, objects, raw)
        barlines = [_bbox(b.bbox) for b in raw["barlines"]]
        oemer_image_path, image_size = raw["image_path"], raw["image_size"]

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
    )


def detect(prep: DocumentPreparation, config, logger: logging.Logger) -> list:
    _ensure_checkpoints(logger)

    counter = {"n": 0}

    def next_id():
        counter["n"] += 1
        return counter["n"]

    results = []
    for page in prep.pages:
        image_path = Path(page.corrected_render_path or page.render_path)
        try:
            results.append(process_page(page.page_number, image_path, config, next_id, logger))
        except Exception as exc:
            logger.error("page %d failed in phase2: %s", page.page_number, exc, exc_info=True)
            results.append(PageDetection(page=page.page_number, error=str(exc)))

    total_objects = sum(len(r.objects) for r in results)
    logger.info("phase2_detect: %d objects detected across %d pages", total_objects, len(results))
    return results
