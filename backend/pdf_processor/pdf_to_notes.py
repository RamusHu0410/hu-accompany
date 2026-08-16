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

from part1_notes import pdf_to_png, png_to_musicxml, musicxml_to_notes
from part2_markings import detect as markings_detect

# A marking only gets attached to a note when their timeline offsets are
# this close (quarter-lengths) -- a straight "nearest marking anywhere on
# the page" match would tag literally every note with whatever marking
# happens to be closest, even pages away. This keeps it to markings that
# actually coincide with that note's onset (anchoring is itself only
# accurate to about a beat -- see part2_markings' anchor.py docstring).
MARKING_MATCH_TOLERANCE_QL = 0.25


def _nearest_marking_text(note_start_ql: float, markings: list) -> "str | None":
    best_text, best_dist = None, None
    for mk in markings:
        dist = abs(mk["offset_ql"] - note_start_ql)
        if dist <= MARKING_MATCH_TOLERANCE_QL and (best_dist is None or dist < best_dist):
            best_text, best_dist = mk["text"], dist
    return best_text


def _build_piece_data(pdf_path: str, bpm: float, time_signature: str,
                       all_notes: list, all_markings: list) -> dict:
    """
    Assembles the combined, whole-piece JSON matching the downstream Rust
    consumer's PieceData/Notes structs. ms fields are converted from the
    quarter-length offsets the rest of this pipeline uses internally
    (ms_per_ql = 60000 / bpm, i.e. one beat's duration at this tempo).

    "curr_phase"/"instrument"/"curr_music_phrase" are playback/session
    state the OMR pipeline has no way to know -- left at their zero
    values for the consumer to fill in. Likewise "vibrato_depth",
    "pedal_action", and "has_accent" aren't detected by this pipeline
    (Part 2 only detects text markings, not graphical symbols -- see
    README's "Known limitations"), so they're always null.
    """
    ms_per_ql = 60000.0 / bpm

    notes = []
    for n in all_notes:
        start_ms = round(n["start"] * ms_per_ql, 3)
        duration_ms = round(n["duration"] * ms_per_ql, 3)
        notes.append({
            "note_id": n["id"],
            "pitch_hz": n["hz"],
            "start_time_ms": start_ms,
            "end_time_ms": round(start_ms + duration_ms, 3),
            "duration_ms": duration_ms,
            "vibrato_depth": None,
            "pedal_action": None,
            "has_accent": None,
            "markings": _nearest_marking_text(n["start"], all_markings),
        })

    piece_dir = Path(pdf_path).resolve().parent
    return {
        "piece_name": f"{piece_dir.parent.name}/{piece_dir.name}",
        "curr_phase": 0,
        "instrument": None,
        "curr_music_phrase": 0,
        "timing": {"bpm": bpm, "time_signature": time_signature},
        "notes": notes,
    }


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
          "markings_json": [markings json paths, one per page],
          "markings_debug_png": [debug png paths, one per page -- detected
                        markings boxed and labeled on a clean copy of the
                        page, separate from "debug_png" above so marking
                        boxes aren't lost among part1_notes' note/clef/
                        barline/accidental boxes],
          "piece_json": path to the combined, whole-piece JSON (also
                        written to disk) -- same content as "piece_data"
                        below, matching the downstream Rust consumer's
                        PieceData/Notes struct shape,
          "bpm":            float,
          "time_signature": str,
          "notes":      [{"id", "hz", "start", "duration"}, ...]  -- combined
                        across all pages, with each page's "start" offset
                        by the running duration of the pages before it,
                        so multi-page pieces form one continuous timeline;
                        "id" is each note's 0-based position in this
                        combined, sorted list (not the same as the
                        page-local "id" in each page's own notes.json),
          "markings":   [{"offset_ql", "type", "value", "text", "confidence"}, ...]
                        -- composer markings (dynamics/tempo/expression/
                        technique/time signature) detected via OCR, combined
                        across all pages onto that same timeline ("offset_ql"
                        lines up with notes' "start" -- both are quarter-length
                        offsets, not seconds),
          "piece_data": {"piece_name", "curr_phase", "instrument",
                        "curr_music_phrase", "timing": {"bpm", "time_signature"},
                        "notes": [{"note_id", "pitch_hz", "start_time_ms",
                        "end_time_ms", "duration_ms", "vibrato_depth",
                        "pedal_action", "has_accent", "markings"}, ...]}
                        -- "notes"/"markings" above reshaped into the
                        Rust-side schema (see _build_piece_data's
                        docstring for field-by-field notes on what this
                        pipeline can and can't fill in),
          "timing":     {"split", "omr", "notes", "markings", "total"}  -- seconds
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
    page_durations = []
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
        page_durations.append(page_duration)
        time_offset += page_duration

        out_path = Path(xml_path).resolve().parent / f"{Path(xml_path).stem}_notes.json"
        with open(out_path, "w") as f:
            json.dump(page_result, f, indent=2)
        notes_json_paths.append(str(out_path))
    notes_time = time.time() - t0

    all_notes.sort(key=lambda n: (n["start"], n["hz"]))
    # Each page's notes.json carries a page-local id (musicxml_to_notes.py);
    # renumber here so "id" reflects each note's position on the combined,
    # multi-page timeline instead.
    for i, n in enumerate(all_notes):
        n["id"] = i

    t0 = time.time()
    markings_json_paths = []
    markings_debug_paths = []
    all_markings = []
    time_offset = 0.0
    for png_path, xml_path, omr_result, page_duration in zip(
        pages, xml_paths, omr_results, page_durations
    ):
        markings_debug_path = str(
            Path(xml_path).resolve().parent / f"{Path(xml_path).stem}_markings_debug.png"
        )
        page_markings = markings_detect.detect_markings(
            ocr_png_path=png_path,
            oemer_image_size=omr_result["image_size"],
            barlines=omr_result["barlines"],
            xml_path=xml_path,
            working_png_path=omr_result["working_png"],
            debug_png_path=markings_debug_path,
        )
        markings_debug_paths.append(markings_debug_path)
        for mk in page_markings:
            all_markings.append({**mk, "offset_ql": round(mk["offset_ql"] + time_offset, 4)})

        out_path = Path(xml_path).resolve().parent / f"{Path(xml_path).stem}_markings.json"
        with open(out_path, "w") as f:
            json.dump(page_markings, f, indent=2)
        markings_json_paths.append(str(out_path))
        time_offset += page_duration
    markings_time = time.time() - t0

    all_markings.sort(key=lambda mk: mk["offset_ql"])

    piece_data = _build_piece_data(pdf_path, bpm, time_signature, all_notes, all_markings)
    piece_json_path = str(Path(pdf_path).resolve().parent / f"{Path(pdf_path).resolve().parent.name}.json")
    with open(piece_json_path, "w") as f:
        json.dump(piece_data, f, indent=2)

    return {
        "pages": pages,
        "musicxml": xml_paths,
        "debug_png": debug_paths,
        "notes_json": notes_json_paths,
        "markings_json": markings_json_paths,
        "markings_debug_png": markings_debug_paths,
        "piece_json": piece_json_path,
        "bpm": bpm,
        "time_signature": time_signature,
        "notes": all_notes,
        "markings": all_markings,
        "piece_data": piece_data,
        "timing": {
            "split": round(split_time, 2),
            "omr": round(omr_time, 2),
            "notes": round(notes_time, 2),
            "markings": round(markings_time, 2),
            "total": round(split_time + omr_time + notes_time + markings_time, 2),
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
    print(f"[1/4] Split PDF -> {len(result['pages'])} page(s): {t['split']}s")
    print(f"[2/4] OMR ({len(result['pages'])} page(s)): {t['omr']}s")
    print(f"[3/4] Note parsing ({len(result['notes'])} note(s)): {t['notes']}s")
    print(f"[4/4] Marking detection ({len(result['markings'])} marking(s)): {t['markings']}s")
    print(f"Total: {t['total']}s")
    print(f"Piece JSON: {result['piece_json']}")
