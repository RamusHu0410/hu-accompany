## Requirements
- oemer
- opencv-python-headless==4.11.0.86
- PyMuPDF
- numpy
- music21
- pytesseract (+ the `tesseract` binary on PATH)

## Pipeline

Two parts, each its own subpackage:

**`part1_notes/`** — split → OMR → note parsing (`pdf_to_png.py`,
`png_to_musicxml.py`, `musicxml_to_notes.py`), each writing its output next
to the input file, matching the `storage/scores/<Composer>/<Piece>/`
layout. These are helper modules only — not meant to be run directly.

**`part2_markings/`** — OCRs each page's rendered PNG (the same one fed to
oemer) for the composer markings oemer's vision pipeline never looks for at all
(dynamics, tempo words, expressions, technique instructions, time
signature), classifies each recognized word against a closed vocabulary
(`vocabulary.py`), and anchors it onto that page's music21 timeline using
barline positions (`anchor.py`). `detect.py` ties OCR detection + anchoring
together and draws each marking's box onto its own debug PNG (a clean copy
of oemer's working image, not part1_notes' already-busy notehead/clef/
barline/accidental overlay — see `<page>_working.png` below), so marking
boxes are easy to pick out by eye. Graphical symbols (hairpins, staccato dots,
accents, fermatas, slurs) are not attempted — that's small-blob shape
classification, a different and harder problem than closed-vocabulary OCR;
see the note detection known-limitations below for why that kind of
heuristic doesn't generalize well on these scores.

`pdf_to_notes.py` is the single entry point that drives both parts, both
as a CLI command and as an importable function. It takes the **original
PDF path**, not a single already-split page PNG — it does the PDF-to-PNG
split itself. (Pointing it at a PNG "works" in the sense that PyMuPDF will
happily open an image file as a fake one-page document, but then every
output gets written as `page-001.*`, not the page number you actually
meant — if you need to redo a single already-split page, call
`part1_notes.png_to_musicxml.convert()` / `part1_notes.musicxml_to_notes.convert()`
directly instead.)

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
  "debug_png":  [...],   # debug png paths, one per page -- notes, clefs,
                          # barlines, and accidentals boxed/labeled
  "notes_json": [...],   # notes json paths, one per page (also written to disk)
  "markings_json": [...],  # markings json paths, one per page (also written to disk)
  "markings_debug_png": [...],  # debug png paths, one per page -- markings
                          # boxed/labeled on a clean copy of the page, kept
                          # separate from "debug_png" above
  "piece_json": ...,     # path to the combined, whole-piece JSON (also
                          # written to disk next to the source PDF, named
                          # after the piece's own storage folder) -- same
                          # content as "piece_data" below
  "bpm": 120, "time_signature": "4/4",
  "notes": [{"id": ..., "hz": ..., "start": ..., "duration": ...}, ...],
            # combined across all pages onto one continuous timeline --
            # "id" is each note's 0-based position in this combined,
            # sorted (by start, then hz) list
  "markings": [{"offset_ql": ..., "type": ..., "value": ..., "text": ...,
                "confidence": ...}, ...],  # combined across all pages onto
            # that same timeline -- "offset_ql" lines up with notes' "start"
            # (both are quarter-length offsets, not seconds)
  "piece_data": {
    "piece_name": "<Composer>/<Piece>",
    "curr_phase": 0, "instrument": None, "curr_music_phrase": 0,
    "timing": {"bpm": 120, "time_signature": "4/4"},
    "notes": [{"note_id": ..., "pitch_hz": ..., "start_time_ms": ...,
               "end_time_ms": ..., "duration_ms": ..., "vibrato_depth": None,
               "pedal_action": None, "has_accent": None, "markings": ...}, ...],
  },  # "notes"/"markings" above, reshaped to match the downstream Rust
      # consumer's PieceData/Notes struct field names and ms-based timing.
      # See _build_piece_data() in pdf_to_notes.py for exactly which
      # fields this pipeline can/can't fill in (short version: anything
      # about playback session state or graphical symbols is null/0,
      # since nothing upstream of this ever determines it).
  "timing": {"split": ..., "omr": ..., "notes": ..., "markings": ..., "total": ...},  # seconds
}
```

`markings["type"]` is one of `"dynamic"`, `"tempo"`, `"expression"`,
`"technique"`, `"time_signature"` — see `part2_markings/vocabulary.py` for
the exact word lists and values.

`piece_data["notes"][i]["markings"]` is only filled in when a marking's
`offset_ql` lands within `MARKING_MATCH_TOLERANCE_QL` (0.25, a sixteenth
note) of that note's own offset — a plain "nearest marking anywhere on the
page" match would tag every single note with whatever marking happens to
be closest, even pages away, which isn't what "this note has this marking"
should mean. Most notes will have `markings: null`; that's expected, not a
detection failure — most notes don't have a marking printed directly at
their onset.

`png_to_musicxml.py` also writes `<page>_working.png` next to its other
output -- a clean, unannotated copy of oemer's resized working image (the
coordinate space every bbox in this pipeline, e.g. barlines, notes, and
rescaled OCR markings, lives in). It's the base image `part2_markings`
draws its debug overlay on top of; not returned in `process()`'s dict since
nothing else consumes it directly.

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

oemer's sharp/flat/natural sub-type classifier (a small pretrained sklearn
model, independent of the matching heuristic above) also misclassifies
accidentals on both test pieces (~15-25% of matched accidentals). Bbox-level
discriminators (fill ratio, aspect ratio) were tried as a pre-filter and
don't separate genuine misclassifications from correct ones — the
confusion happens inside the classifier's own feature space, not in
candidate selection, so this is documented as a known limitation rather
than patched.

Dotted-rhythm detection (`oemer/rhythm_extraction.py: parse_dot`) was
also investigated. Its per-notehead dot check is a pixel-area heuristic
(prone to noise), and it forces all noteheads within the same
stem-group (chord) to share one dot status by majority vote. That
group-level uniformity is musically correct for chords (one dot glyph
covers the whole chord), so it was left as-is — the real source of any
dot errors is the underlying per-notehead pixel-area classifier, which
would need retuning or replacing (not attempted here for lack of
ground-truth data to validate against).

`part2_markings`' barline-interpolation anchoring is an approximation, not
an exact readout — engraving spaces text roughly proportionally to
duration, not exactly — so a marking can land a beat or so off from its
true position, though it should reliably land in the right measure.

`ocr_detect.py` uses two confidence floors, not one: 0.6 for dynamics
(`p`/`f`/`ff`/etc.), 0.3 for everything else. Dynamics are 1-3 character
tokens that dense engravings misread stems/beams/blank staff gaps as
constantly (measured: every such false positive on a test page scored
<= 0.43), so they need a strict floor; longer, more distinctive words
("scherzando", "cresc.") essentially never arise by coincidence from
misread notation ink, so they get a much lower one (measured: a real
"cresc." scored only 0.49 — a strict floor would have dropped it).
Longer words also get a fuzzy-match fallback (`vocabulary.py`) since OCR
misreads a correctly-segmented word's letters ("Crese." for "cresc.")
far more often than it spells a whole different vocabulary word by
coincidence.

Even so, tesseract's page segmentation sometimes fails to isolate a
marking as a text token at all when scanning the whole page in one
pass -- not a low-confidence read, no read whatsoever. `ocr_detect.py`
mitigates this by also OCRing overlapping horizontal strips of the page
(upscaled 2x) and merging both passes' results, which recovers some but
not all of these (measured on a real, marking-dense page: went from 3
correctly-detected markings to 11 after the vocabulary/threshold/tiling
work, up from ~17 markings visible on the page by eye -- "sf", "ff",
"fz", a second "cresc." instance, and "accel" were still missed in a
given run). Apple's Vision framework (macOS's built-in OCR) was also
evaluated as an alternative: it's much faster and reads multi-word
phrases more coherently ("Allegro scherzando (Moto primo)" as one
string) but is far more conservative about what counts as text, so it
misses even more of the short isolated dynamics than tesseract does --
not adopted. A real fix would need a music-notation-specific text
detector or a proper multi-engine ensemble, not more tuning of either
engine alone.

`part2_markings`' anchoring, once the OCR misreads above are accounted
for, is otherwise unaffected by this — a marking that's never read as
text at all just never becomes an anchoring candidate in the first
place; there's no silent corruption downstream, only missing markings.

`piece_data`'s `curr_phase`, `instrument`, and `curr_music_phrase` are
playback/session state that nothing in this OMR pipeline determines --
they're always `0`/`null` placeholders for the downstream consumer to
fill in. Likewise `vibrato_depth`, `pedal_action`, and `has_accent` are
always `null`: they'd require graphical-symbol detection (hairpins,
pedal markings, accent wedges), which is explicitly out of scope for
`part2_markings` (it only reads text) -- see the pipeline section above.
