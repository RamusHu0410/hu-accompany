Feedback generation, in two phases: phase 1 judges one phrase at a time,
phase 2 summarizes the whole session.

Run everything from `backend/` with `DYLD_LIBRARY_PATH=/opt/homebrew/lib`
(libvips isn't on the default linker path on macOS).

## 1. Layout

```
feedback_generator/
  orchestrator.py   wiring only -- parse, align, call judges, return dicts
  summarizer.py     phase 2 -- aggregates every phrase into one summary
  store.py          reads/writes storage/feedback/
  errors.py
  judges/           all feedback text and all 0-100 ratings live here
    __init__.py     shared notes/context/Finding types, pitch + bar math,
                    thresholds, judge registry
    phase1/         one phrase at a time
      __init__.py     JUDGES = run order
      pitch.py        intonation, wrong notes
      rhythm.py       note onsets (early/late) and note lengths
      tempo.py        pulse drift across a phrase
      articulation.py staccato / legato / marcato vs. markings
      notes.py        notes not played, notes not written
      dynamics.py     no loudness data upstream -- scores null, says nothing
      pedaling.py     no pedal data upstream -- scores null, says nothing
    phase2/         the whole session at once
      __init__.py     JUDGES = run order
      era.py          style-period performance practice
```

- Each judge owns one dimension: its detection, its rating, its wording.
- Judge contract, same in both phases: `NAME`, `PHASE` (1 or 2),
  `judge(ctx) -> JudgeResult`. Phase 1 gets a `PhraseContext` (that phrase's
  aligned notes), phase 2 a `PieceContext` (every stored phrase, aggregated
  scores, every finding).
- Nothing outside `judges/` writes feedback text; nothing outside
  `summarizer.py` aggregates across phrases.
- Adding a dimension = one new file in `judges/phase1/` or `judges/phase2/`
  + one entry in that package's `JUDGES`.

## 2. Storage

```
storage/feedback/<date>-<piece>/       e.g. 2026-09-07-Prelude_in_C
  Phase1/
    Phrase1.json    one file per phrase
    Phrase2.json
  Phase2/
    Summary.json    summarizer.py
    Era.json        judges/phase2/era.py
```

- No DB table -- JSON on disk, like `pdf_processor`'s piece_data.
- Session directory defaults to today's date + the piece title, so phrases
  of one piece group themselves; pass `session_id` to target one explicitly.
- Phrases are 1-based, and re-sending a phrase overwrites just that file.
- Phase 2 is re-runnable: each run overwrites `Phase2/` with a snapshot of
  every phrase stored so far.
- Piece metadata (title/composer/composed_date) is stored in each phase-1
  file header; phase 2 reads it back from there.

Phase-1 file:

```json
{"piece": {...}, "recorded_at": "...", "phrase": 1, "bpm": 96.0,
 "time_signature": "4/4", "bars": [1, 4],
 "scores": {"overall": 85, "pitch": 79, "rhythm": 92, "tempo": null,
            "dynamics": null, "articulation": null},
 "feedback": [{"bars": 1,
               "box": {"page": 1, "x": 412, "y": 903, "w": 305, "h": 330,
                       "page_size": [2262, 3200]},
               "category": "pitch", "severity": "major",
               "confidence": 1.0, "message": "...", "details": {...}}]}
```

- `feedback` is the unit everywhere -- phase 2 uses the same shape.
- `bars` on a finding = the bar it happened in, numbered from the piece
  start using `bpm` + `time_signature`; `bars` on the file = the span.
- `box` is that same bar as a pixel rectangle on the score, so the app can
  mark the spot instead of making the player count bars. It comes from
  `pdf_processor`'s `<Piece>_bars.json`, passed in as `judge_phrase`'s
  `bar_boxes` (`/api/feedback/phrase`'s `bar_boxes`); without it every
  `box` is `null`. Pixels are measured on the page PNG whose dimensions
  `page_size` gives, so a client rendering the PDF at another resolution
  scales by its own width/height. Phase 2's summary findings carry
  `details.boxes` -- every bar box behind that recurring problem.
- `severity` is `minor`/`major`; `confidence` is 0.5 at the "this is an
  error" threshold, rising to 1.0 for an unmistakable one.
- `details` carries the numbers behind the call (cents, ms, ratio) plus a
  `suggestion`.
- A `null` score means that judge had nothing to measure, and it drops out
  of `overall` instead of counting as zero. `dynamics` and `pedaling` are
  always null: no note schema upstream (mobile app / native_ffi /
  pdf_processor) carries loudness or pedal events.

## 3. Quick test

```
python manage.py test feedback_generator.tests api.tests -v 2
```

- 77 tests, no server needed.
- Writes nothing into `backend/storage/` — `STORAGE_ROOT` points at a temp dir.

## 4. Debug test to storage

```
python manage.py runserver 0.0.0.0:8000
```

Phase 1 — POST one phrase (the same request the app sends,
`frontend/lib/Send_Strings_2Server.dart`):

```
curl -s -X POST http://127.0.0.1:8000/api/feedback/phrase \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": 1,
    "timing": {"bpm": 96, "time_signature": "4/4"},
    "piece": {"title": "Prelude in C", "composer": "Bach", "composed_date": "1722"},
    "expected_notes": [
      {"note_id": 1, "pitch_hz": 261.63, "start_time_ms": 0,   "end_time_ms": 625,  "duration_ms": 625},
      {"note_id": 2, "pitch_hz": 293.66, "start_time_ms": 625, "end_time_ms": 1250, "duration_ms": 625}
    ],
    "user_notes": [
      {"note_id": 1, "pitch_hz": 261.63, "start_time_ms": 0,   "end_time_ms": 625,  "duration_ms": 625},
      {"note_id": 2, "pitch_hz": 277.18, "start_time_ms": 765, "end_time_ms": 1390, "duration_ms": 625}
    ]
  }' | python -m json.tool
```

- Note 2 is a semitone flat and 140 ms late, so there's something to say;
  `expected_notes` must be non-empty, `user_notes` may be (silence -> every
  note comes back missing).
- The response ends with what it wrote:

```
    "session_id": "2026-09-07-Prelude_in_C",
    "stored_at": "storage/feedback/2026-09-07-Prelude_in_C/Phase1/Phrase1.json"
```

- Send `"phrase": 2` with the same `session_id` for the next phrase; reuse a
  phrase number to overwrite that take.
- Use the LAN address (`ipconfig getifaddr en0`) to test from the phone.

Phase 2 — summarize everything stored for that session:

```
curl -s -X POST http://127.0.0.1:8000/api/feedback/summary \
  -H "Content-Type: application/json" \
  -d '{"session_id": "2026-09-07-Prelude_in_C"}' | python -m json.tool
```

- Writes `Phase2/Summary.json` (piece-wide scores, top 3 recurring
  problems, what went well, one-line summary) and `Phase2/Era.json`.
- 404 if the session has no phase-1 phrases yet.
- `backend/storage/` is **not** gitignored — clean up with
  `rm -r storage/feedback`.

## 5. `judges/phase2/era.py` status

- Structure only: date parsing, era detection and the per-era trait tables
  work; the `_<era>_feedback` builders and `build_era_summary` are
  deliberately unimplemented, so `Era.json` comes out with
  `era`/`label`/`traits` filled in and `feedback: []`.

```
python -c "
from feedback_generator.judges.phase2.era import parse_composed_year, detect_era, adjacent_era
for d in [1722, '1810', 'ca. 1785', '1830s', '1802-1804', '18th century', None, 'unknown']:
    y = parse_composed_year(d); e = detect_era(d); a = adjacent_era(y)
    print(repr(d), '->', y, e.label if e else None, '| adjacent:', a.label if a else None)
"
```

- Expect `1722 -> 1722 Baroque`, `'1810' -> 1810 Classical | adjacent: Romantic`
  (within `TRANSITION_MARGIN_YEARS` of 1820), `'1830s' -> 1835`,
  `'1802-1804' -> 1803` (midpoint), `'18th century' -> 1750`.
- `None`/`''`/`'unknown' -> None None`, i.e. the era section stays empty.
- Once the builders produce prose, extend `EraDetectionTests`/`JudgePieceTests`
  in `tests.py` with the boundary years (1749/1750, 1819/1820).
