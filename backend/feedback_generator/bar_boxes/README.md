Per-bar pixel boxes for a rendered page, so a finding can be highlighted
where it happened on the score instead of naming a bar number the player
then hunts for.

Run everything from `backend/` with `DYLD_LIBRARY_PATH=/opt/homebrew/lib`
(libvips isn't on the default linker path on macOS).

## 1. Layout

```
feedback_generator/
  bar_boxes/
    bar_boxes.py   build() -- oemer staff/barline detections -> one pixel
                   box per bar, numbered from 1 in reading order
    tests.py       pure-geometry tests (no oemer, no real page)
```

- `build(barlines, staffs, oemer_image_size, page_size)` runs on oemer's
  own detections, already in memory after `png_to_musicxml.convert()` calls
  `extract()`. A bar's box is the x-span between the barlines around it and
  the padded y-span of the whole system it sits on, rescaled from oemer's
  working image into the page PNG's pixels.
- Returns `[{"bar", "x", "y", "w", "h"}, ...]` for one page, or `[]` when
  oemer found no staffs. See the `bar_boxes.py` docstring for the two
  approximations (system-edge boundaries, reading-order numbering).

## 2. Where it flows

- `pdf_processor`'s `pdf_to_notes._collect_bar_boxes` stitches every page
  onto one piece-wide numbering and writes `<Piece>_bars.json`.
- `orchestrator.judge_phrase` takes that list as `bar_boxes` and attaches
  each finding's `box` -- the same rectangle the parent README's phase-1
  file shows. Without it every `box` is `null`.

## 3. Quick test

```
python manage.py test feedback_generator.bar_boxes.tests -v 2
```

- 7 tests, no server needed, nothing written to disk.

## 4. Live API test

Start Django from `backend/`:

```
DYLD_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python manage.py runserver 127.0.0.1:8000
```

In another terminal, submit feedback with the bar boxes from the score:

```
curl -s -X POST http://127.0.0.1:8000/api/feedback/phrase \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": 1,
    "timing": {"bpm": 96, "time_signature": "4/4"},
    "bar_boxes": [
      {"bar": 1, "page": 1, "x": 412, "y": 903, "w": 305, "h": 330,
       "page_size": [2262, 3200]}
    ],
    "expected_notes": [
      {"note_id": 1, "pitch_hz": 293.66, "start_time_ms": 0,
       "end_time_ms": 625, "duration_ms": 625}
    ],
    "user_notes": [
      {"note_id": 1, "pitch_hz": 277.18, "start_time_ms": 0,
       "end_time_ms": 625, "duration_ms": 625}
    ]
  }' | .venv/bin/python -m json.tool
```

The response should include a finding with the matching `box`. Omitting
`bar_boxes` should return the same finding with `"box": null`.

Stop the server with `Control-C`. The request writes a phase-1 file under
`storage/feedback/`.
