"""
Run oemer OMR on a single PNG and save the resulting MusicXML.

Usage:
    python png_to_musicxml.py <path/to/page.png>
"""

import os
import sys
import types
from pathlib import Path

import numpy as np
# oemer 0.1.5 uses np.int / np.float / np.bool, removed in NumPy 1.24+.
for _alias, _builtin in (("int", int), ("float", float), ("bool", bool), ("complex", complex)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _builtin)

from oemer.ete import extract, clear_data

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "musicxml"


def convert(png_path: str) -> str:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    args = types.SimpleNamespace(
        img_path=png_path,
        output_path=str(STORAGE_DIR),
        use_tf=False,
        save_cache=False,
        # Deskewing crashes on some scanned pages (AssertionError in
        # oemer/dewarp.py); disabled since input pages are pre-cropped.
        without_deskew=True,
    )
    clear_data()
    return extract(args)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 png_to_musicxml.py <path/to/image.png>")
        sys.exit(1)

    png_path = sys.argv[1]
    if not os.path.exists(png_path):
        print(f"File not found: {png_path}")
        sys.exit(1)

    out_path = convert(png_path)
    print(f"MusicXML written to: {out_path}")
