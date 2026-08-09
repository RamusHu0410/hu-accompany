"""
Run the full pipeline (split -> OMR -> note parsing) on a PDF.

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


def process(pdf_path: str) -> dict:
    """
    Split, run OMR, and parse notes for every page of a PDF.

    Returns:
        {
          "pages":      [png paths, one per page],
          "musicxml":   [musicxml paths, one per page],
          "debug_png":  [debug png paths, one per page -- detected
                        noteheads/clefs/barlines/etc. boxed and labeled],
          "notes_json": [notes json paths, one per page],
          "bpm":            float,
          "time_signature": str,
          "notes":      [{"hz", "start", "duration"}, ...]  -- combined
                        across all pages, with each page's "start" offset
                        by the running duration of the pages before it,
                        so multi-page pieces form one continuous timeline,
          "timing":     {"split", "omr", "notes", "total"}  -- seconds
        }
    """
    t0 = time.time()
    pages = pdf_to_png.convert(pdf_path)
    split_time = time.time() - t0

    t0 = time.time()
    omr_results = [png_to_musicxml.convert(page) for page in pages]
    xml_paths = [r["musicxml"] for r in omr_results]
    debug_paths = [r["debug_png"] for r in omr_results]
    omr_time = time.time() - t0

    t0 = time.time()
    notes_json_paths = []
    all_notes = []
    time_offset = 0.0
    bpm = None
    time_signature = None
    for xml_path in xml_paths:
        page_result = musicxml_to_notes.convert(xml_path)
        if bpm is None:
            bpm = page_result["bpm"]
            time_signature = page_result["time_signature"]

        page_notes = page_result["notes"]
        for n in page_notes:
            all_notes.append({**n, "start": round(n["start"] + time_offset, 4)})
        page_duration = max((n["start"] + n["duration"] for n in page_notes), default=0.0)
        time_offset += page_duration

        out_path = Path(xml_path).resolve().parent / f"{Path(xml_path).stem}_notes.json"
        with open(out_path, "w") as f:
            json.dump(page_result, f, indent=2)
        notes_json_paths.append(str(out_path))
    notes_time = time.time() - t0

    all_notes.sort(key=lambda n: (n["start"], n["hz"]))

    return {
        "pages": pages,
        "musicxml": xml_paths,
        "debug_png": debug_paths,
        "notes_json": notes_json_paths,
        "bpm": bpm,
        "time_signature": time_signature,
        "notes": all_notes,
        "timing": {
            "split": round(split_time, 2),
            "omr": round(omr_time, 2),
            "notes": round(notes_time, 2),
            "total": round(split_time + omr_time + notes_time, 2),
        },
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pdf_to_notes.py <path/to/score.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    result = process(pdf_path)
    t = result["timing"]
    print(f"[1/3] Split PDF -> {len(result['pages'])} page(s): {t['split']}s")
    print(f"[2/3] OMR ({len(result['pages'])} page(s)): {t['omr']}s")
    print(f"[3/3] Note parsing ({len(result['notes'])} note(s)): {t['notes']}s")
    print(f"Total: {t['total']}s")
