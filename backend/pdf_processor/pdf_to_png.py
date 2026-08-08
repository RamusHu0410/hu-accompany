"""
Split a PDF music score into one PNG per page.

Usage:
    python pdf_to_png.py <path/to/score.pdf>
"""

import os
import sys
from pathlib import Path

import fitz  # PyMuPDF

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "pages"


def convert(pdf_path: str, dpi: int = 200) -> list:
    out_dir = STORAGE_DIR / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
        out_path = out_dir / f"page-{i+1:03d}.png"
        pix.save(str(out_path))
        paths.append(str(out_path))
    doc.close()
    return paths


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pdf_to_png.py <path/to/score.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    pages = convert(pdf_path)
    print(f"{len(pages)} page(s) written to: {Path(pages[0]).parent}")
    for p in pages:
        print(f"  {p}")
