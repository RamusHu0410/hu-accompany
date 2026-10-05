# AUDIO BACKEND SERVICES

The Rust audio engine. It listens to the microphone, follows a known piece
note by note, and streams what it hears to the Flutter app, which sends it to
the Python feedback backend.

It is a **score follower**, not a free pitch detector: it only listens for
the notes of the piece that is currently loaded. With no piece loaded, the
microphone runs but nothing is detected.

## Core Functionalities Provided

### Functions Dart can call

Bridged through flutter_rust_bridge (`frontend/lib/src/rust/api.dart`):

| Rust | Dart | What it does |
|---|---|---|
| `init_session(json_data)` | `initSession(jsonData:)` | Loads the piece to follow (see [PieceData](#piecedata)). Also clears anything left over from the previous recording. Call it before every recording. |
| `notes_stream(sink)` | `notesStream()` | Subscribes to detected notes. Rust sends a batch each time a note ends. |
| `get_user_data()` | `getUserData()` | JSON of the entries gathered but not yet sent. The app reads it when recording stops, to recover the note that was still sounding. |

Plain C exports, **not** bridged (marked `#[frb(ignore)]`):

| Rust | C wrapper (`frontend/ios/recording_bridge.c`) | What it does |
|---|---|---|
| `listen_audio()` | `start_recording()` | Opens the default microphone and starts the analysis thread. |
| `stop_audio()` | `stop_recording()` | Closes the microphone. The analysis thread ends by itself. |

Dart calls the C wrappers with `dart:ffi` from
`frontend/lib/integrations/audio/Audio_Native.dart`.

### PieceData

What `init_session` expects. Parsing is strict: every field must be present
with the right type, or the call fails.

```json
{
  "piece_name": "C major scale",
  "curr_phase": 0,
  "instrument": null,
  "curr_music_phrase": 0,
  "timing": { "bpm": 60.0, "beat_unit": 4 },
  "notes": [
    {
      "note_id": 1,
      "pitch_hz": 523.25,
      "start_time_ms": 0.0,
      "end_time_ms": 1000.0,
      "duration_ms": 1000.0,
      "is_end": false,
      "vibrato_depth": null,
      "pedal_action": null,
      "has_accent": null,
      "markings": null
    }
  ]
}
```

- `curr_phase` must be `0` or `1`. Phases `2` and `3` exist in the code but do
  nothing yet, so audio is ignored.
- The first note's `start_time_ms` should be `0`: the clock starts at the
  first note (see below).
- `is_end` marks the last note of a phrase. Rust copies it onto what it
  detects, and the app uses it to tell when a bar is finished.
- `timing` needs `beat_unit`. The backend's `/api/score/process` returns
  `time_signature` instead, so its `piece_data` cannot be passed in as-is.

### What Dart receives

Each batch is a list of `Notes`. For every note heard there are two kinds of
entry:

- **Live** entries, one per analysis step while the note sounds:
  `end_time_ms` is `null` and `duration_ms` is the length so far.
- One **completed** entry when the note stops: `end_time_ms` is set, and
  `pitch_hz` is the median of what was heard.

A batch is sent every time a note completes, and holds everything gathered
since the previous batch. The backend and the app both keep only the longest
entry per `note_id`, which is the completed one.

## How detection works

1. **Capture** at the device's own sample rate (48 kHz on iPhones and Macs).
2. **Analyse** a 1024-sample window every 128 samples, with a Hann window
   applied before the FFT. Quiet windows (RMS ≤ 0.0075) are skipped.
3. **Start the clock at the first note.** Time does not advance until the
   piece's first note is heard. The delay between opening the microphone and
   the first samples arriving is longer than the matching window below, so a
   clock started at capture could never line up with the score.
4. **Pick candidate notes**: every note whose window
   `[start − 85 ms, end + 85 ms]` contains the current time.
5. **Pick the one being played**: the loudest candidate above the volume
   threshold. On a tie (a repeated pitch), the note that is due now wins.
   This assumes one note at a time.
6. **Track each note** from its first frame to the frame it stops, then send
   the batch.

Pitch is read around the loudest of the three FFT bins nearest the target
note and refined by parabolic interpolation. At 48 kHz one bin is about
47 Hz.

## Changes made on 2026-09-30

Found while preparing the first real-instrument test. The detection fixes
have tests in `src/dsp.rs` (see [Tests](#tests)). Three changes have no unit
test and were only checked in the simulated performance described below,
which is not in the repo: the first-note clock, the removed panics in
`listen_audio`, and clearing on load. Your original `test_c4_pitch_detection`
still passes, with its call updated to the new signature.

| Problem | Effect | Fix |
|---|---|---|
| `process_dsp` locked `USER_DATA` a second time on the same thread when a note ended | The audio thread froze the first time any note ended, so nothing was ever sent to Dart | Use the lock already held |
| Sample rate hardcoded to 44100 | On 48 kHz hardware, pitches read about 1.5 semitones flat, and the clock ran 8.8% fast, losing the score after about a second | `create_stream` returns the real rate, which is passed through |
| Completed note reported the score's expected pitch | Every note looked perfectly in tune | Report the median of the pitches heard |
| One start time shared by all notes | Where two notes' windows overlap (every note change) one note's start reset the other's | A `NoteTrack` per note |
| No FFT window | In-tune notes read up to ±25 cents off (the backend calls 25 "slightly out"), and a ringing note spilled into neighbouring notes' bins | Hann window in `run_fft` |
| Pitch interpolated around the target bin, not the loudest one | A note played a semitone sharp was reported 80 cents flat | Interpolate around the peak |
| Every candidate above the threshold counted as sounding | The previous note still ringing started the next note 85 ms early | Loudest candidate only |
| Clock started when capture started | Start-up latency alone could exceed the 85 ms window | Start the clock at the first note |
| `listen_audio` could panic (no microphone, unsupported format) | A panic inside a C export aborts the whole app | Return an error and log it |
| `init_session` kept old entries | A recording stopped mid-note leaked into the next one | Clear `USER_DATA` on load |

A simulated 48 kHz performance (with overtones, one note a semitone sharp and
one 60 ms late) through the real capture loop now gives:

- one completed entry per note, and no false starts;
- in-tune notes within 6 cents, and timing within 3 ms;
- the sharp note at about +103 cents, and the late note at +61 ms.

## Tests

```sh
cd native_ffi
cargo test --lib
```

| Test | Guards against |
|---|---|
| `test_c4_pitch_detection` | The original check that C4 is detected |
| `a_note_ending_does_not_freeze_the_audio_thread` | The deadlock |
| `in_tune_notes_read_in_tune_at_48k` | Sample-rate and window accuracy, C4 to C6 |
| `a_wrong_note_is_reported_in_the_right_direction` | Interpolating around the wrong bin |
| `median_of_what_was_heard` | Reporting the expected pitch |
| `a_ringing_note_does_not_start_the_next` | False early starts |

## Building for iOS

The app links these libraries statically. After changing anything in
`native_ffi`, rebuild both and copy them into the app:

```sh
cd native_ffi
export IPHONEOS_DEPLOYMENT_TARGET=13.0
cargo build --release --target aarch64-apple-ios       # real iPhone
cargo build --release --target aarch64-apple-ios-sim   # simulator
cp target/aarch64-apple-ios/release/libnative_ffi.a     ../frontend/ios/libnative_ffi.a
cp target/aarch64-apple-ios-sim/release/libnative_ffi.a ../frontend/ios/libnative_ffi_sim.a
```

One-time setup: `rustup target add aarch64-apple-ios aarch64-apple-ios-sim`.

If you changed anything in `mod api` (the bridged functions), also
regenerate the Dart bindings:

```sh
cd frontend
flutter_rust_bridge_codegen generate
```

The bridge checks a hash of the Rust source when the app starts. If the
bindings and the library do not match, the app logs
`[Diagnostics] rust: bridge unavailable` and nothing Rust-based works.

flutter_rust_bridge is now pinned to **2.13.0** on both sides
(`Cargo.toml` and `frontend/pubspec.yaml`). The installed code generator was
2.13, and it bumps both pins from 2.12.0 when it runs.

macOS builds do not link this library at all, so Rust features are
unavailable there.

## Known limitations

- **Coarse frequency resolution.** Bins are about 47 Hz wide, so pitch is
  more reliable in higher registers: around C4 a semitone is a third of a
  bin, around C5 two thirds.
- **One note at a time.** Chords and sustained piano pedal will confuse the
  "loudest candidate" rule.
- **Strict timing.** Notes more than 85 ms from where the score expects them
  fall outside their window and are not recognised.
- **Fixed volume threshold.** Very quiet playing may not register, and very
  loud playing can make a neighbouring note look like it is sounding.
- **`get_current_targets` clones every note of the piece on each analysis
  step.** Fine for short pieces, and worth fixing for long ones.
