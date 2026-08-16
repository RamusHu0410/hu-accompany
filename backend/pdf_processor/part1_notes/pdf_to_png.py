"""
Split a PDF music score into one PNG per page.
Output PNGs are written next to the source PDF, matching the
storage/scores/<Composer>/<Piece>/ layout.

Called from pdf_to_notes.process() -- not meant to be run standalone.
"""

from pathlib import Path

import fitz  # PyMuPDF


def convert(pdf_path: str, dpi: int = 200) -> list:
    out_dir = Path(pdf_path).resolve().parent

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
