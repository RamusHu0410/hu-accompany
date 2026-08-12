## Requirements
- oemer
- opencv-python-headless==4.11.0.86
- PyMuPDF
- numpy
- music21

## Pipeline

Internally three stages (split → OMR → note parsing), each in its own
file (`pdf_to_png.py`, `png_to_musicxml.py`, `musicxml_to_notes.py`) and
each writing its output next to the input file, matching the
`storage/scores/<Composer>/<Piece>/` layout. Those three files are
helper modules only — not meant to be run directly.

`pdf_to_notes.py` is the single entry point that drives all three, both
as a CLI command and as an importable function.

**Run from the command line**
```bash
backend/.venv/bin/python3 backend/pdf_processor/pdf_to_notes.py "<path/to/score.pdf>"
```

**Or call it from other Python code**
```python
from pdf_to_notes import process
result = process("<path/to/score.pdf>")
```
Returns a dict:
```python
{
  "pages":      [...],   # png paths, one per page
  "musicxml":   [...],   # musicxml paths, one per page
  "notes_json": [...],   # notes json paths, one per page (also written to disk)
  "bpm": 120, "time_signature": "4/4",
  "notes": [{"hz": ..., "start": ..., "duration": ...}, ...],  # combined
            # across all pages onto one continuous timeline
  "timing": {"split": ..., "omr": ..., "notes": ..., "total": ...},  # seconds
}
```

## Known limitations

`png_to_musicxml.py` always disables oemer's deskew step
(`without_deskew=True`), since it crashes on some scanned pages
(`AssertionError: -1, -1` in `oemer/dewarp.py`). Page skew is not
auto-corrected.

`png_to_musicxml.py` also monkey-patches oemer's
`get_nearby_note_id` (accidental → notehead matching). Stock oemer scans
a single pixel row to the right of each accidental and takes the first
notehead hit; on dense/chordal pages that row easily misses by a couple
pixels or grabs the wrong notehead, silently dropping the accidental
(measured ~48% drop rate on a dense piano-reduction page vs ~23% on a
sparse single-voice one). The patch searches a small 2D window instead
and picks the nearest notehead pixel by Euclidean distance, cutting the
drop rate roughly in half (dense page: 48% → 26%; sparse page: 23% →
14%). Some misattribution still happens on very dense chords — this is
a heuristic, not a real fix of oemer's underlying note detection.

Dotted-rhythm detection (`oemer/rhythm_extraction.py: parse_dot`) was
also investigated. Its per-notehead dot check is a pixel-area heuristic
(prone to noise), and it forces all noteheads within the same
stem-group (chord) to share one dot status by majority vote. That
group-level uniformity is musically correct for chords (one dot glyph
covers the whole chord), so it was left as-is — the real source of any
dot errors is the underlying per-notehead pixel-area classifier, which
would need retuning or replacing (not attempted here for lack of
ground-truth data to validate against).
