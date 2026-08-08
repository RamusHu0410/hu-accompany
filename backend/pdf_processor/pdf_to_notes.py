"""
Run the full pipeline (split -> OMR -> note parsing) on a PDF and report
how long each step took.

Usage:
    python pdf_to_notes.py <path/to/score.pdf>
"""

import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pdf_to_png
import png_to_musicxml
import musicxml_to_notes


def run(pdf_path: str) -> None:
    t0 = time.time()
    pages = pdf_to_png.convert(pdf_path)
    split_time = time.time() - t0
    print(f"[1/3] Split PDF -> {len(pages)} page(s): {split_time:.2f}s")

    t0 = time.time()
    xml_paths = []
    for page in pages:
        xml_paths.append(png_to_musicxml.convert(page))
    omr_time = time.time() - t0
    print(f"[2/3] OMR ({len(pages)} page(s)): {omr_time:.2f}s")

    t0 = time.time()
    musicxml_to_notes.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    total_notes = 0
    for xml_path in xml_paths:
        result = musicxml_to_notes.convert(xml_path)
        out_path = musicxml_to_notes.STORAGE_DIR / f"{Path(xml_path).stem}_notes.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        total_notes += len(result["notes"])
    notes_time = time.time() - t0
    print(f"[3/3] Note parsing ({total_notes} note(s)): {notes_time:.2f}s")

    print(f"Total: {split_time + omr_time + notes_time:.2f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pdf_to_notes.py <path/to/score.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    run(pdf_path)
