# Running the PDF processor

The actual pipeline lives at `backend/scripts/pdf_processor.py`. It takes a
**PDF** path (not a PNG) — it renders each page to PNG internally via
PyMuPDF (`fitz`), then runs `oemer` (OMR) → MusicXML → `music21` on each
page.

## Command

From the repo root, using the project's venv (already has `oemer`, `fitz`,
`music21`, `numpy` installed):

```bash
backend/.venv/bin/python3 backend/scripts/pdf_processor.py "<path/to/score.pdf>"
```

Example:

```bash
backend/.venv/bin/python3 backend/scripts/pdf_processor.py \
  "backend/storage/scores/Chopin/Etude_No.1_Op.10/IMSLP37119-PMLP01969-Chopin_Klavierwerke_Band_2_Peters_Op.10_600dpi.pdf"
```

Equivalently, with the venv activated:

```bash
source backend/.venv/bin/activate
python backend/scripts/pdf_processor.py "<path/to/score.pdf>"
```

## Output

Written next to the input PDF:
- `<name>_notes.json` — note events (`hz`, `start`, `duration`, `dynamic`) plus bpm/time signature
- `<name>_annotated.pdf` — copy of the score with every detected notehead boxed and color-coded by duration

## Known limitation

`image_to_musicxml()` in `pdf_processor.py` always runs oemer with
`without_deskew=False`. Some scanned pages (e.g. high-DPI IMSLP scans)
trip an assertion in oemer's dewarp step
(`AssertionError: -1, -1` in `oemer/dewarp.py`). When that happens the
script catches the exception per-page, logs
`oemer failed on page N: ...`, and continues with the remaining pages —
it does not fall back to `--without-deskew` automatically.
