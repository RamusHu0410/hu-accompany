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

from oemer.ete import extract, clear_data
from oemer.draw_teaser import teaser


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
    teaser().save(debug_path)

    return {"musicxml": mxl_path, "debug_png": debug_path}
