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
| `listen_audio() -> i32` | `start_recording()` | Opens the default microphone and starts the processing thread. Returns `0` (also when already recording) or an [error code](#audio-intake-and-session-lifecycle). |
| `stop_audio()` | `stop_recording()` | Closes the microphone and returns at once. The processing thread finishes the audio already captured and sends the note still sounding. |
| `audio_status() -> i32` | `recording_status()` | `0`, or the code of the latest problem since the recording started. Poll it while recording. |
| `audio_error_message(buf, cap) -> usize` | `recording_message()` | The message that goes with the status, as UTF-8. |

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
- The score's clock starts at the first note the player is heard to play
  (see [The score's clock](#the-scores-clock)). Its `start_time_ms` is
  usually `0`; any value works.
- `is_end` marks the last note of a phrase. Rust copies it onto what it
  detects, and the app uses it to tell when a bar is finished.
- `timing` needs `beat_unit`. The backend's `/api/score/process` returns
  `time_signature` instead, so its `piece_data` cannot be passed in as-is.

### What Dart receives

Each batch is a list of `Notes`. A note is sent **once, when it ends** (or
when recording stops, if it is still sounding): `start_time_ms`, `end_time_ms`
and `duration_ms` are set, `pitch_hz` is the median of what was heard, and
`note_id` is the score note it matches. Times are in the score's clock, in
milliseconds. A note is delivered a few hundred milliseconds after it ends
(median ~0.5 s on real piano, longer for notes that ring on).

If Dart has stopped listening, notes stay in `get_user_data()` instead of
being lost.

## How detection works

1. **Capture** at the device's own sample rate (48 kHz on iPhones and Macs).
2. **Analyse** a 1024-sample window every 128 samples, with a Hann window
   applied before the FFT. Quiet windows (RMS ≤ 0.0075) are skipped.
3. **Start the clock at the first note.** Score time 0 is where the player's
   first note is heard (see [The score's clock](#the-scores-clock)).
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

## The score's clock

Notes are matched within ±85 ms of where the score puts them, but the
microphone is opened before the player starts: the app counts in four beats
and opens it one beat before the downbeat (500-1500 ms at practice tempi), and
the system adds its own start-up delay. A clock that starts with the first
sample is off by that much. On real piano (MAESTRO) with silence in front of
the audio, `cargo run --release --example timing -- fixtures/real/maestro_heldout --no-anchor --lead-ms N`:

| mic open N ms before the music | notes found | onsets within ±85 ms (of those found) |
|---|---|---|
| 0 | 95.1% | 98.2% |
| 100 | 93.2% | 4.5% (median error +111 ms) |
| 200 | 57.8% | 32.7% |
| 500 | 47.1% | 67.5% |

So the tracker (`NoteTracker::anchored`, on by default; `ANCHOR_CLOCK` in
`lib.rs`) listens for the piece's opening note(s) at any time, and when one is
heard sets score time 0 to its start. With it the same recordings give
94.8-95.0% found and onset error within ±25 ms for any lead from 100 to 1500 ms.

Consequences:

- The first note is reported exactly at its scored time; every other note is
  timed **relative to the player's first note**, so how long the player waited
  before starting is not judged.
- Until the opening note is heard, nothing else is listened for. A player who
  never plays it (or a piece whose first pitch never sounds) gets no notes.
- It is set again for every piece: loading another piece while recording
  starts over with that piece's first note.
- Samples that were never captured cannot be recovered: if the microphone opens
  *after* the player has started, the clock starts at the first note that *is*
  heard.

## Audio intake and session lifecycle

```
cpal callback ──> bounded queue (2048 chunks) ──> processing thread ──> notes_stream
 (downmix only)   <── empty buffers come back ──   (tracker, pitch network)
```

- **Capture** uses the device's own format: any sample format cpal reports is
  converted to f32, any channel count is averaged to mono, any rate is passed
  on (the pitch network resamples to 22.05 kHz). The callback takes ~2 µs per
  1024-frame stereo buffer, does not block and, once the buffers are warm, does
  not allocate. If the processing thread were ever 12-24 s behind, the callback
  drops audio and reports `7` rather than grow the queue: timing is wrong after
  that.
- **Errors** reach Dart as a code (`listen_audio`'s return value, then
  `audio_status`) and a message (`audio_error_message`), never only stderr:

  | code | meaning |
  |---|---|
  | 1 | no microphone found |
  | 2 | the microphone's format could not be read (also what a host with no sound card reports) |
  | 3 | sample format not supported |
  | 4 | the OS refused to open the microphone (busy, no permission, no audio session) |
  | 5 | the microphone opened but would not start |
  | 6 | the stream failed while recording (device unplugged, route change) |
  | 7 | processing fell behind; audio was dropped |
  | 8 | processing thread failed, or the previous recording has not finished |
  | 9 | no audio for 2 s (interruption, device asleep) |
  | 100 | warning: the input is pure digital silence for 1 s (permission denied or hardware muted, which iOS reports as silence, not as an error) |
  | 101 | warning: the pitch network could not load; DSP evidence is used |

  Nothing on the FFI path panics: the C exports and the processing thread are
  wrapped, and a panic is reported as `8`.
- **Stop and restart**: `stop_audio` returns at once. `init_session`,
  `get_user_data` and `listen_audio` first wait (up to 3 s) for the previous
  recording's processing thread to finish, so its last notes are delivered
  before anything is cleared or read, and cannot land in the next session.
  `init_session` clears `USER_DATA`.
- **The piece** is read by the processing thread when it builds its tracker (at
  the first frame after a piece is loaded in phase 0 or 1). Loading another piece
  while the microphone is open drops that tracker, **including notes of the old
  piece that had not ended yet**, and follows the new piece from its first note.
- **iOS** does none of the audio session work in Rust. `AppDelegate.swift`
  asks for microphone permission and sets the session to play-and-record in
  measurement mode (no gain control or filtering) before capture, through the
  `hu_accomponist/audio_session` channel that `Audio_Native.dart` calls.
- **Android** is not wired up in this repository (`frontend/android` does not
  exist).

### Real-time cost

`cargo run --release --example realtime -- <wav> <piece.json>` replays a clip
at live speed. On one core of the development container, 30 s clips of real
piano:

| evidence | processing thread CPU | behind live at the end | note delivered after it ended |
|---|---|---|---|
| neural (default) | 52-54% of a core | 170-180 ms | median 0.5-0.6 s, p90 0.9-1.2 s, max 3.3 s |
| DSP only | 6-8% | 0-1 ms | 140-150 ms |

The network accounts for all of it: one run takes ~100 ms on that core and runs
every 186 ms (`RUN_EVERY_FRAMES`). A device whose core is ~1.9x slower cannot
keep up. Measure on the target phones; `RUN_EVERY_FRAMES = 32` halves the cost
for ~90 ms more delay.

### Timing accuracy

`cargo run --release --example timing -- <dir>` reports start and end error
against a directory of clips. Real piano (MAESTRO, 6 clips, 1848 notes), error
of reported time against the key press and release:

| | before | now |
|---|---|---|
| onset, median (p10 .. p90) | -21 ms (-45 .. +4) | +11 ms (-3 .. +35), clock from sample 0; -2 ms (-23 .. +28) anchored |
| end, median (p10 .. p90) | +399 ms (+151 .. +895) | +92 ms (-6 .. +419) |
| note length, median | not measured | +70 ms |

Ends were late because the network's confidence on a silent key is ~0.1 (and
higher with any room noise), which is where `sustain_confidence` sat, so a
release only counted once the output had completely decayed. Start and end are
now stamped where the note's confidence crosses 75% of its own peak
(`Thresholds::edge_relative`). The remaining ~+70 ms on piano is the damper and
room; notes that ring on (low octaves sharing harmonics with a sounding note)
are the +400 ms tail.

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
| `tracker::test_*anchor*`, `audio::test_clock_starts_at_the_first_note_*` | The clock, for any mic lead; a piece that opens with a chord or a rest; stopping before the first note |
| `tracker::test_end_is_stamped_where_the_level_fell_*` and two more | End stamps follow the release, not the noise floor, without cutting held notes short or splitting them |
| `audio::capture_tests::*` | Sample formats, no allocation in the callback, a stuck consumer, the error status, silent input, stalled stream |
| `lifecycle_tests::*` | Waiting for the last recording's notes, nothing stale in the next session, switching pieces while recording, the C error message |

`cargo test --lib` runs on any machine with the ALSA headers
(`libasound2-dev`) and needs no fixtures. These need downloaded fixtures
and are ignored by default:

- `cargo test --test real_audio -- --ignored`: GuitarSet
  (`fixtures/real/fetch_guitarset.py`, from zenodo.org), plus
  `fixtures/real/silent_room_*.wav` recordings of your own.
- The same with `REAL_AUDIO_DIR=fixtures/real/maestro_heldout` runs the
  piano set (`fixtures/real/fetch_maestro.py`, from storage.googleapis.com). It
  only has `_comp` clips: pass `real_guitar_chords` as a filter.
- `examples/timing.rs` and `examples/realtime.rs` take any directory of
  WAV + PieceData JSON.

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
