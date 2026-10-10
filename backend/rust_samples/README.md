# Rust → Python sample payloads

Real output of the Rust note detector (`native_ffi`), kept here to check that it
matches what `POST /api/feedback/phrase` accepts.

| File | What it is |
|---|---|
| `<name>.rust_output.json` | **Raw detector output**: the array of `Notes` that `get_user_data()` returns and `notes_stream` delivers to Dart. Nothing edited. |
| `<name>.phrase_request.json` | The request body the app sends to `/api/feedback/phrase`, built from the file above plus the score. |
| `build_request.py` | Builds the request from the raw output and runs it through the real `judge_phrase`. |

Two clips, both rendered piano (not a human performance), from `native_ffi/fixtures/piano/rendered/`:
`01_scale_solo` (29 single notes) and `12_melody_over_chords_comp` (44 notes, chords).

## What Rust produces

Each element is one detected note, sent **once, when it ends**:

```json
{"note_id": 1, "pitch_hz": 262.8, "start_time_ms": 500.0, "end_time_ms": 743.8,
 "duration_ms": 243.8, "is_end": false,
 "vibrato_depth": null, "pedal_action": null, "has_accent": null, "markings": null}
```

- `note_id` is the **score** note the detector matched, not a running counter.
- Records come out in order of when notes **end**, not score order (`1, 3, 2, 4, …`).
  Chords overlap heavily, so the order is more scrambled there. Python sorts and aligns them itself.
- `is_end` copies the score note's phrase-end flag. It can sit anywhere in the array.
- In real detector output `start_time_ms`, `end_time_ms` and `duration_ms` are always numbers.
  The Rust type is `Option<f32>`, so they can be `null` in the type, but `tracker.rs` always fills them.
- `vibrato_depth`, `pedal_action`, `has_accent` and `markings` are `null` today.

## Compatibility with the Python backend

Checked against `feedback_generator.judge_phrase` (the function behind the view):

| Case | Result |
|---|---|
| Rust JSON sent as-is (extra keys `is_end`, `vibrato_depth`, …) | Accepted; extra keys are ignored. |
| Mapped the way the Dart app does it (`build_request.py`) | Accepted. Scale: overall 99; chords clip: overall 99. |
| `user_notes` empty (silence) | Accepted; every expected note is reported missing, overall 0. |
| A note with `null` `start_time_ms` or `duration_ms` | **`TypeError` inside `judge_phrase`, which the view returns as HTTP 500, not 400.** |

The last row cannot happen today: the Rust tracker never emits nulls, and
`Phrase_send2_server.dart` (`_userNoteToJson`) replaces any null before sending.
But the Python side does not validate this itself, so another client sending a null would get a 500.
This was left unchanged on purpose.

The few minor rhythm findings in the samples are detector timing noise on clean synthetic audio, not format problems.

## Assumptions in the request files

`build_request.py` copies the Dart mapping rules; these requests were **not** captured from a running app.
`PieceData` has `bpm` and `beat_unit` but no time signature, so `"time_signature": "4/4"` is assumed.
`piece` carries only the fixture's name. `expected_notes` are the fixture's notes without `is_end`.

## Regenerate

From `native_ffi/` (the first build compiles `tract-onnx` and takes a few minutes):

```bash
cargo run --release --example dump_json -- \
  fixtures/piano/rendered/01_scale_solo.wav fixtures/piano/rendered/01_scale_solo.json \
  --out ../backend/rust_samples/01_scale_solo.rust_output.json
```

Then from `backend/`:

```bash
python rust_samples/build_request.py rust_samples/01_scale_solo.rust_output.json \
  ../native_ffi/fixtures/piano/rendered/01_scale_solo.json rust_samples/01_scale_solo.phrase_request.json
```

## Provenance

Generated 2026-10-10 from `origin/main` @ `284faec6` (`native_ffi` exported with `git archive`, release build,
default detector settings: neural evidence on, score clock anchored to the first note heard).
Re-run after changing the detector, since the numbers depend on it. The output shape depends only on `native_ffi/src/models.rs`.
