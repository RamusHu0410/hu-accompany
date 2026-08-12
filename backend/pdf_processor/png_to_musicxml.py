"""
Run oemer OMR on a single PNG and save the resulting MusicXML plus a
debug PNG (detected noteheads/clefs/barlines/etc. boxed and labeled).
Output is written next to the source PNG, matching the
storage/scores/<Composer>/<Piece>/ layout.

Called from pdf_to_notes.process() -- not meant to be run standalone.
"""

import types
from pathlib import Path

import numpy as np
# oemer 0.1.5 uses np.int / np.float / np.bool, removed in NumPy 1.24+.
for _alias, _builtin in (("int", int), ("float", float), ("bool", bool), ("complex", complex)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _builtin)

import oemer.symbol_extraction as _sym_ext
from oemer.bbox import get_center
from oemer.utils import get_unit_size


def _get_nearby_note_id(box, note_id_map):
    """
    Replaces oemer's stock get_nearby_note_id, which scans a single pixel
    row to the right of the accidental and takes the first notehead pixel
    it hits. On dense/chordal pages that row often misses the notehead by
    a couple pixels or hits the wrong one in a chord, silently dropping
    the accidental (measured ~48% drop rate on a dense piano-reduction
    page vs ~23% on a sparse single-voice one).

    Instead, search a 2D window around the accidental and pick whichever
    notehead pixel is nearest (Euclidean) to the accidental's center.
    """
    cen_x, cen_y = get_center(box)
    unit_size = int(round(get_unit_size(cen_x, cen_y)))
    y1 = max(0, box[1] - unit_size // 2)
    y2 = min(note_id_map.shape[0], box[3] + unit_size // 2)
    x1 = box[2]
    x2 = min(note_id_map.shape[1], box[2] + unit_size * 2)

    region = note_id_map[y1:y2, x1:x2]
    ys, xs = np.where(region != -1)
    if len(ys) == 0:
        return None

    dists = (ys + y1 - cen_y) ** 2 + (xs + x1 - cen_x) ** 2
    nearest = np.argmin(dists)
    return int(region[ys[nearest], xs[nearest]])


_sym_ext.get_nearby_note_id = _get_nearby_note_id

import cv2
from PIL import Image
from oemer import layers
from oemer.ete import extract, clear_data
import oemer.draw_teaser as _draw_teaser

ACCIDENTAL_COLOR = (255, 0, 255)  # magenta
DOT_COLOR = (0, 255, 255)  # cyan


def _teaser() -> Image.Image:
    """
    Replaces oemer's stock teaser(), which only draws a box for
    accidentals that failed to match a notehead (sfn.note_id is None) --
    successfully-matched ones are never drawn at all, so the debug image
    can only ever show failures, never confirm a correct detection.

    Draws every accidental (sharp/flat/natural -- oemer's model has no
    double-sharp/double-flat class, so those can't appear) in one colour
    regardless of match status, and marks augmentation dots in another
    colour. oemer doesn't keep a bbox for the dot glyph itself (parse_dot
    only records a boolean has_dot per note), so its position is
    approximated just right of the notehead using the same unit_size
    scale parse_dot used for its scan window.
    """
    ori_img = layers.get_layer('original_image')
    notes = layers.get_layer('notes')
    groups = layers.get_layer('note_groups')
    barlines = layers.get_layer('barlines')
    clefs = layers.get_layer('clefs')
    sfns = layers.get_layer('sfns')
    rests = layers.get_layer('rests')

    out = np.copy(ori_img).astype(np.uint8)

    def draw_bbox(bboxes, color, text=None, labels=None, text_y_pos=1):
        for idx, (x1, y1, x2, y2) in enumerate(bboxes):
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            y_pos = y1 + round((y2 - y1) * text_y_pos)
            label = text if text is not None else labels[idx]
            cv2.putText(out, label, (x2 + 2, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

    draw_bbox([gg.bbox for gg in groups], color=(255, 192, 92), text="group")
    draw_bbox([n.bbox for n in notes if not n.invalid], color=(194, 81, 167),
               labels=[str(n.label)[0] for n in notes if not n.invalid])
    draw_bbox([b.bbox for b in barlines], color=(63, 87, 181), text='barline', text_y_pos=0.5)
    draw_bbox([c.bbox for c in clefs], color=(235, 64, 52), labels=[c.label.name for c in clefs])
    draw_bbox([r.bbox for r in rests], color=(12, 145, 0), labels=[r.label.name for r in rests])
    draw_bbox([s.bbox for s in sfns], color=ACCIDENTAL_COLOR, labels=[s.label.name for s in sfns])

    for note in notes:
        if note.invalid or not getattr(note, 'has_dot', False):
            continue
        x1, y1, x2, y2 = note.bbox
        cen_y = (y1 + y2) // 2
        unit_size = get_unit_size((x1 + x2) // 2, cen_y)
        dot_x = int(x2 + unit_size * 0.6)
        cv2.circle(out, (dot_x, cen_y), max(3, int(unit_size * 0.15)), DOT_COLOR, -1)

    for note in notes:
        if note.label is not None:
            x1, y1, x2, y2 = note.bbox
            cv2.putText(out, note.label.name[0], (x2 + 2, y2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 70, 255), 2)

    return Image.fromarray(out)


_draw_teaser.teaser = _teaser


def convert(png_path: str) -> dict:
    out_dir = Path(png_path).resolve().parent
    args = types.SimpleNamespace(
        img_path=png_path,
        output_path=str(out_dir),
        use_tf=False,
        save_cache=False,
        # Deskewing crashes on some scanned pages (AssertionError in
        # oemer/dewarp.py); disabled since input pages are pre-cropped.
        without_deskew=True,
    )
    clear_data()
    mxl_path = extract(args)

    # teaser() reads oemer's global layer state left behind by extract(),
    # so it must run before the next convert() call clears it.
    debug_path = str(Path(mxl_path).with_name(Path(mxl_path).stem + "_debug.png"))
    _draw_teaser.teaser().save(debug_path)

    return {"musicxml": mxl_path, "debug_png": debug_path}
