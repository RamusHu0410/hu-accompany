## Requirements
- oemer
- opencv-python-headless==4.11.0.86
- PyMuPDF
- numpy
- music21

## Pipeline

Three stages, one script each. Run in order, each stage's output feeds the next.

**1. Split PDF into per-page PNGs**
```bash
backend/.venv/bin/python3 backend/pdf_processor/pdf_to_png.py "<path/to/score.pdf>"
```
Writes `backend/storage/pages/<pdf_name>/page-001.png`, `page-002.png`, ...

**2. Run OMR on a page PNG → MusicXML**
```bash
backend/.venv/bin/python3 backend/pdf_processor/png_to_musicxml.py "<path/to/page.png>"
```
Writes `backend/storage/musicxml/<page_name>.musicxml`

**3. Parse MusicXML → timed note events**
```bash
backend/.venv/bin/python3 backend/pdf_processor/musicxml_to_notes.py "<path/to/page.musicxml>"
```
Writes `backend/storage/notes/<page_name>_notes.json` — each note has `hz`, `start`, `duration` (start/duration in quarter-note beats).

## Known limitation

`png_to_musicxml.py` always disables oemer's deskew step
(`without_deskew=True`), since it crashes on some scanned pages
(`AssertionError: -1, -1` in `oemer/dewarp.py`). Page skew is not
auto-corrected.
