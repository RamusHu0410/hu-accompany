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

## Known limitation

`png_to_musicxml.py` always disables oemer's deskew step
(`without_deskew=True`), since it crashes on some scanned pages
(`AssertionError: -1, -1` in `oemer/dewarp.py`). Page skew is not
auto-corrected.
