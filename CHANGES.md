# What changed (Sep 18 – Sep 30, 2026)

A summary of the work on the app, the Rust audio engine and the backend over
these two weeks: what changed, why, and what is still open. For detail, see:

- `frontend/README.md` — the app: layout, the recording flow, iOS build setup
- `native_ffi/README.md` — the Rust engine: API, how detection works, fixes
- `backend/quiz/README.md` — the quiz backend

---

## Needs action from the team

1. **The OMR pipeline doesn't work** (`/api/score/process`, backend). It is
   the step that should read notes off a PDF, and it fails in two places:
   - `image_enhancer/enhancer_script.py`: `enhance_music_pdf` enhances each
     page but never writes `output_pdf_path`, which `pdf_to_notes.py` opens
     next. It also prints "All pages are processed!" even when every page
     failed, because `concurrent.futures.wait` doesn't raise page errors.
   - oemer's model files aren't installed (`oemer/checkpoints/unet_big/model.onnx`
     is missing in `.venv`).

   Until this works, **real PDF scores can't be practised**, only the
   built-in exercises. When it does work, note that its `piece_data` is not
   in Rust's format: `timing` has `time_signature` where Rust needs
   `beat_unit`, and notes have no `is_end`. The app will have to convert it,
   as `Exercise.toPieceData()` does.

2. **Quiz route not connected.** The quiz backend (`backend/quiz/`) is
   complete, but Django can't reach it until one line is added to
   `backend/api/urls.py`:
   ```python
   path("", include("quiz.urls")),   # and import `include` from django.urls
   ```

3. **Rust owner: please review** the changes in `native_ffi/src/dsp.rs`,
   `audio.rs` and `lib.rs`. They are listed with reasons in
   `native_ffi/README.md`, and the detection fixes have tests. Two are design changes
   rather than bug fixes: the clock starts at the first note heard, and only
   the loudest candidate note counts as sounding.

4. **flutter_rust_bridge is now 2.13.0** (it was pinned to 2.12.0). The
   installed code generator bumped `Cargo.toml` and `pubspec.yaml` together
   when it ran. To go back, install codegen 2.12.0 and regenerate.

5. **`backend/api/mdns.py` advertises `<name>.local.local`.** On macOS
   `socket.gethostname()` already ends in `.local`, and the code adds another.
   The app now works around this, but the backend fix is one line. Consider
   also `register_service(info, allow_name_change=True)`: at the moment a
   second server starting (or a stale announcement) crashes Django with
   `NonUniqueNameException`.

6. **Housekeeping**
   - `frontend/ios/Runner/recording_bridge.c` is an unused copy. Only
     `frontend/ios/recording_bridge.c` is compiled.
   - `frontend/lib/integrations/audio/Dart_ffi_bridge.dart` (`AudioBridge`)
     is unused.
   - `how-to-run.md` says to change the address in `Send_Strings_2Server.dart`.
     That's no longer needed: the app finds the server over mDNS.
   - `backend/api/README.md` is out of date: `/api/score/process` returns
     `piece_data` directly, and the feedback and quiz routes aren't listed.

---

## Real-instrument practice

**Before these changes, playing a real instrument produced no feedback at
all.** Four separate problems each stopped it:

| Problem | Where | Fix |
|---|---|---|
| The app never told Rust which piece to follow, so Rust listened for nothing | App | Exercises are loaded with `initSession` before each recording |
| Rust's audio thread froze the first time a note ended, so nothing was ever sent | Rust | Deadlock fixed |
| Rust assumed 44.1 kHz on 48 kHz hardware: pitch read ~1.5 semitones flat, and tracking was lost after ~1 s | Rust | The real sample rate is used |
| No source of expected notes: OMR is broken (see above) | Backend | Built-in exercises for now |

Testing on simulated audio then found more Rust problems that made feedback
meaningless: completed notes reported the written pitch, so everything looked
in tune; a ringing note started the next one early; sharp notes read flat;
and in-tune notes read up to ±25 cents off. All are fixed. See
`native_ffi/README.md`.

**New in the app:**

- Three exercises (C major scale, arpeggio, Twinkle) at 60/80/100 bpm, with a
  choice of octave.
- A 4-beat count-in, a metronome pulse, and the current note highlighted.
- Bars are sent to the backend one at a time as you finish them.

**Result:** a simulated performance through the real Rust loop and the real
backend judge detects every note once. In-tune notes read within 6 cents and
timing within 3 ms, and a deliberately wrong note comes back as *"Wrong note —
you played F5 instead of E5."* It has not been tried with a real instrument
yet.

## iOS builds (simulator and real phone)

- **Simulator:** it failed to link because Xcode built an x86_64 slice, while
  the Rust library is arm64-only. x86_64 is now excluded for the simulator.
- **Rust loading on iOS:** the library is linked statically, but the
  generated loader looked for a dynamic framework. `Rust_Bridge.dart` now
  looks up symbols in the running app instead.
- **Real phone:** every build used to link the *simulator* library. The phone
  library is now built, and each platform links its own.
- **Release builds:** the linker removed the Rust bridge, since nothing calls
  it directly, and hid the C mic functions. Both are kept now.

Verified: simulator and phone builds (debug, signed debug, release) all
succeed. The release build contains every function the app looks up at
runtime.

## Phrase feedback UI

- **Feedback card** (`Phrase_Feedback_Pill`): overall score, per-area scores,
  and up to 3 findings, most severe first. Areas the backend can't measure
  (dynamics, pedalling) are hidden rather than shown as 0.
- **Companion** (`Practice_Companion`): the character's expression follows
  the score. It uses three bands (80+, 55+, below) defined once in
  `Phrase_Feedback.dart`, so the companion, card, recorder glow and drawer
  always agree.

## Backend connection fixes (app side)

- Notes from Rust are now sent in the backend's format. Before, they were
  sent as a placeholder string, and the backend would have rejected every
  phrase.
- The composer of the picked score is passed through instead of dropped.
- `[Diagnostics]` terminal logging covers discovery, every request, and why a
  request failed.
- Import casing fixed (`Pull_back_Phrase` vs `Pull_back_phrase`). It worked
  on macOS by accident and would fail on Linux or CI.

## Navigation and score view

- Picking a sheet from the **search** record now opens practice. Before, it
  returned you to the home screen.
- Tapping a sheet on the **shelf** now downloads it and opens practice.
- The score can be **zoomed**: pinch, or double-tap to zoom and double-tap
  again to reset.

## Quiz (new feature)

- **Backend:** new module `backend/quiz/`, with no existing files changed.
  145 hand-written questions across six eras, generated from a heading like
  `RCM HISTORY 10 + ARCT CHEAT SHEET / The Middle Ages`. Needs the one-line
  route above.
- **App:** `features/quiz/` has home, session and results screens. It is
  reached from a **QUIZ** record on the turntable.

## App structure and polish

- **Reorganised by screen** into `features/`, `integrations/` and `shared/`,
  with `package:` imports. `frontend/README.md` has the layout.
- **Design tokens** for spacing, corner radius, animation timing and shadows,
  and every colour named in `Color_Theme.dart`.
- **Performance:** the home screen, recorder and library search no longer
  rebuild the whole screen on every frame or keystroke.
- **Polish:** loading skeletons, a friendlier empty shelf, press feedback and
  haptics, and a smoother boot spin.

## Local environment (no code changes)

- **Postgres had no tables:** migrations were never run after switching from
  SQLite. Run `python manage.py migrate`.
- **Port 5432 taken:** a Homebrew Postgres conflicted with Docker's on that
  port. Stop it with `brew services stop postgresql@16`.
- **Flutter's engine cache lost a file**, which broke iOS builds. Repaired
  with `flutter precache --ios --force`.
