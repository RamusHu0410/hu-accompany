mod frb_generated; /* AUTO INJECTED BY flutter_rust_bridge. This line may not be accurate, and you can change it according to your needs. */
// Modules
pub mod audio;
pub mod dsp;
pub mod joint;
pub mod models;
pub mod run_onnx;
pub mod templates;
pub mod tracker;
pub mod volume;

// Crates
use crate::frb_generated::StreamSink;
use flutter_rust_bridge::frb;
use once_cell::sync::Lazy;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::RwLock;
use std::sync::{Condvar, LazyLock, Mutex, MutexGuard};
use std::time::Duration;

// Custom Defined types
use models::{Notes, PieceData, SendStream};

static NOTES_SINK: RwLock<Option<StreamSink<Vec<Notes>>>> = RwLock::new(None);
static ACTIVE_STREAM: Lazy<Mutex<Option<SendStream>>> = Lazy::new(|| Mutex::new(None));
pub static ACTIVE_PIECE: LazyLock<Mutex<Option<PieceData>>> = LazyLock::new(|| Mutex::new(None));
pub static USER_DATA: LazyLock<Mutex<Option<Vec<Notes>>>> = LazyLock::new(|| Mutex::new(None));
/// Counts piece loads (init_session). The processing thread follows the
/// piece that was loaded when it looked; a changed count makes it start over.
pub static PIECE_GENERATION: AtomicU64 = AtomicU64::new(0);
/// Use the pitch network (run_onnx.rs) as the note evidence; false = DSP only.
pub static USE_NEURAL: AtomicBool = AtomicBool::new(true);
/// Start the score's clock at the player's first note instead of when the mic
/// opened (see tracker::NoteTracker::anchored). The app counts the player in
/// with the mic already open, so this must stay on there.
pub static ANCHOR_CLOCK: AtomicBool = AtomicBool::new(true);
/// Learned note shapes of the player's instrument (calibration), if any.
pub static NOTE_TEMPLATES: LazyLock<Mutex<Option<templates::NoteTemplates>>> = LazyLock::new(|| Mutex::new(None));

/// Whether the processing thread of the last recording is still running.
static WORKER_RUNNING: Mutex<bool> = Mutex::new(false);
static WORKER_STOPPED: Condvar = Condvar::new();
/// Longest wait for that thread: it only has the audio still queued to finish.
const WORKER_TIMEOUT: Duration = Duration::from_secs(3);

/// A panic elsewhere must not turn every later call into one: these globals
/// stay usable, because every write to them is a single assignment.
pub(crate) fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// Marks the processing thread as finished when dropped, even if it panicked.
struct WorkerGuard;

impl Drop for WorkerGuard {
    fn drop(&mut self) {
        *lock(&WORKER_RUNNING) = false;
        WORKER_STOPPED.notify_all();
    }
}

/// Waits until the last recording's processing thread has delivered its final
/// notes. False if it is still running after `timeout`.
fn wait_for_worker(timeout: Duration) -> bool {
    let running = lock(&WORKER_RUNNING);
    let (running, _) = WORKER_STOPPED
        .wait_timeout_while(running, timeout, |running| *running)
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    !*running
}

/// No panic may cross the FFI boundary: it would abort the whole app.
fn ffi_guard<T>(on_panic: T, f: impl FnOnce() -> T) -> T {
    catch_unwind(AssertUnwindSafe(f)).unwrap_or_else(|_| {
        audio::report(audio::AUDIO_ERR_WORKER, "internal error in the audio engine");
        on_panic
    })
}

/// Opens the microphone and starts the processing thread.
/// Returns `audio::AUDIO_OK` (also when already recording) or an error code;
/// `audio_error_message` says what went wrong.
#[frb(ignore)]
#[unsafe(no_mangle)]
pub extern "C" fn listen_audio() -> i32 {
    ffi_guard(audio::AUDIO_ERR_WORKER, || {
        let mut stream_guard = lock(&ACTIVE_STREAM);
        if stream_guard.is_some() {
            return audio::AUDIO_OK;
        }
        // A restart right after a stop: the last recording's notes go out first.
        if !wait_for_worker(WORKER_TIMEOUT) {
            let message = "the previous recording is still being processed";
            audio::report(audio::AUDIO_ERR_WORKER, message);
            return audio::AUDIO_ERR_WORKER;
        }
        audio::clear_status();
        let capture = match audio::Capture::open() {
            Ok(capture) => capture,
            Err(e) => {
                audio::report(e.code, e.message);
                return e.code;
            }
        };
        let audio::Capture { stream, sample_rate, chunks, recycle } = capture;
        *lock(&WORKER_RUNNING) = true;
        let spawned = std::thread::Builder::new().name("audio-processing".into()).spawn(move || {
            let _guard = WorkerGuard;
            ffi_guard((), || audio::start_processing_loop_with(chunks, sample_rate, Some(recycle)));
        });
        match spawned {
            Ok(_) => {
                *stream_guard = Some(SendStream(stream));
                audio::AUDIO_OK
            }
            Err(e) => {
                *lock(&WORKER_RUNNING) = false;
                audio::report(audio::AUDIO_ERR_WORKER, format!("could not start the processing thread: {e}"));
                audio::AUDIO_ERR_WORKER
            }
        }
    })
}

/// Turns the microphone off. Returns at once: the processing thread finishes
/// the audio already captured and delivers the notes still sounding.
#[frb(ignore)]
#[unsafe(no_mangle)]
pub extern "C" fn stop_audio() {
    ffi_guard((), || {
        // Dropping the stream object turns off the microphone hardware
        let stream = lock(&ACTIVE_STREAM).take();
        drop(stream);
    })
}

/// `audio::AUDIO_OK`, or the code of the latest problem (see audio.rs).
/// Codes from `audio::AUDIO_WARN_SILENT_INPUT` on are warnings.
#[frb(ignore)]
#[unsafe(no_mangle)]
pub extern "C" fn audio_status() -> i32 {
    audio::status()
}

/// Copies the message of the latest problem into `buf` (UTF-8, NUL-terminated,
/// cut to `cap` bytes). Returns the number of bytes written, without the NUL.
///
/// # Safety
/// `buf` must be null or valid for writes of `cap` bytes.
#[frb(ignore)]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn audio_error_message(buf: *mut u8, cap: usize) -> usize {
    ffi_guard(0, || {
        if buf.is_null() || cap == 0 {
            return 0;
        }
        let message = audio::status_message();
        // Cut on a character boundary so Dart can decode what it gets.
        let mut n = message.len().min(cap - 1);
        while !message.is_char_boundary(n) {
            n -= 1;
        }
        unsafe {
            std::ptr::copy_nonoverlapping(message.as_ptr(), buf, n);
            *buf.add(n) = 0;
        }
        n
    })
}

mod api {
    use super::*;
    use crate::models::Notes;
    pub fn init_session(json_data: String) {
        let piece_data: PieceData = serde_json::from_str(&json_data).unwrap();

        // Switching pieces right after a stop: the last recording's notes are
        // delivered first, so they cannot land in this session.
        if lock(&ACTIVE_STREAM).is_none() {
            wait_for_worker(WORKER_TIMEOUT);
        }

        *lock(&ACTIVE_PIECE) = Some(piece_data);
        PIECE_GENERATION.fetch_add(1, Ordering::AcqRel);

        // A new session starts clean. Notes left over from a recording that
        // was stopped mid-note would otherwise be sent with the next one.
        *lock(&USER_DATA) = None;
    }

    // FRB handles returning standard Strings and frees the memory safely.
    pub fn get_user_data() -> String {
        // After a stop, the final notes are still being delivered.
        if lock(&ACTIVE_STREAM).is_none() {
            wait_for_worker(WORKER_TIMEOUT);
        }
        let user_data = lock(&USER_DATA);
        serde_json::to_string(&*user_data).unwrap_or_else(|_| "{}".to_string())
    }
    pub fn notes_stream(s: StreamSink<Vec<Notes>>) {
        *NOTES_SINK.write().unwrap_or_else(|e| e.into_inner()) = Some(s);
    }
}

#[cfg(test)]
mod lifecycle_tests {
    use super::*;
    use std::f32::consts::PI;

    fn piece_json(note_id: u64) -> String {
        format!(
            r#"{{"piece_name":"t","curr_phase":0,"instrument":null,"curr_music_phrase":0,
            "timing":{{"bpm":60.0,"beat_unit":4}},"notes":[{{"note_id":{note_id},"pitch_hz":440.0,
            "start_time_ms":0.0,"end_time_ms":500.0,"duration_ms":500.0,"is_end":false,
            "vibrato_depth":null,"pedal_action":null,"has_accent":null,"markings":null}}]}}"#
        )
    }

    fn note(note_id: u64) -> Notes {
        Notes {
            note_id,
            pitch_hz: 440.0,
            start_time_ms: Some(0.0),
            end_time_ms: Some(500.0),
            duration_ms: Some(500.0),
            is_end: false,
            vibrato_depth: None,
            pedal_action: None,
            has_accent: None,
            markings: None,
            volume: None,
        }
    }

    /// A4 with harmonics, then silence, at 44.1 kHz.
    fn a4(tone_ms: usize, silence_ms: usize) -> Vec<f32> {
        let n = |ms: usize| ms * 44100 / 1000;
        let mut audio: Vec<f32> = (0..n(tone_ms))
            .map(|i| (1..=6).map(|k| 0.3 / k as f32 * (2.0 * PI * 440.0 * k as f32 * i as f32 / 44100.0).sin()).sum())
            .collect();
        audio.extend(vec![0.0; n(silence_ms)]);
        audio
    }

    fn notes_in_user_data() -> Vec<u64> {
        lock(&USER_DATA).iter().flatten().map(|n| n.note_id).collect()
    }

    #[test]
    fn test_waiting_for_the_worker_ends_when_it_does_and_gives_up_when_it_does_not() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        assert!(wait_for_worker(Duration::from_millis(10)), "nothing running: no wait");

        *lock(&WORKER_RUNNING) = true;
        let started = std::time::Instant::now();
        let worker = std::thread::spawn(|| {
            let _guard = WorkerGuard;
            std::thread::sleep(Duration::from_millis(100));
        });
        assert!(wait_for_worker(Duration::from_secs(5)));
        assert!(started.elapsed() >= Duration::from_millis(90), "returned before the worker finished");
        worker.join().unwrap();

        *lock(&WORKER_RUNNING) = true; // a worker that never finishes
        assert!(!wait_for_worker(Duration::from_millis(30)));
        *lock(&WORKER_RUNNING) = false;
    }

    #[test]
    fn test_a_panicking_worker_still_counts_as_finished() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        *lock(&WORKER_RUNNING) = true;
        let worker = std::thread::spawn(|| {
            let _guard = WorkerGuard;
            ffi_guard((), || panic!("tracker bug"));
        });
        worker.join().unwrap(); // ffi_guard swallowed it
        assert!(wait_for_worker(Duration::from_secs(1)));
        assert_eq!(audio::status(), audio::AUDIO_ERR_WORKER);
        audio::clear_status();
    }

    #[test]
    fn test_loading_a_piece_waits_for_the_last_recordings_final_notes_then_clears_them() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        // Recording A was stopped; its worker is still delivering the note that
        // was sounding. Loading piece B must not let that note into B's session.
        *lock(&USER_DATA) = Some(vec![note(1)]);
        *lock(&WORKER_RUNNING) = true;
        let worker = std::thread::spawn(|| {
            let _guard = WorkerGuard;
            std::thread::sleep(Duration::from_millis(100));
            lock(&USER_DATA).get_or_insert_with(Vec::new).push(note(2));
        });
        let generation = PIECE_GENERATION.load(Ordering::Acquire);
        api::init_session(piece_json(7));
        worker.join().unwrap();
        assert_eq!(notes_in_user_data(), Vec::<u64>::new(), "stale notes leaked into the new session");
        assert_eq!(PIECE_GENERATION.load(Ordering::Acquire), generation + 1);
        assert_eq!(api::get_user_data(), "null");
    }

    #[test]
    fn test_reading_leftovers_after_a_stop_includes_the_note_that_was_still_sounding() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        *lock(&USER_DATA) = None;
        *lock(&WORKER_RUNNING) = true;
        let worker = std::thread::spawn(|| {
            let _guard = WorkerGuard;
            std::thread::sleep(Duration::from_millis(100));
            lock(&USER_DATA).get_or_insert_with(Vec::new).push(note(5));
        });
        let json = api::get_user_data();
        worker.join().unwrap();
        assert!(json.contains("\"note_id\":5"), "{json}");
        *lock(&USER_DATA) = None;
    }

    #[test]
    fn test_loading_another_piece_mid_recording_follows_the_new_piece_from_its_first_note() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        audio::clear_status();
        api::init_session(piece_json(9601));
        let (tx, rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || audio::start_processing_loop(rx, 44100));

        // Piece 1's note, played 700 ms into the recording, and a pause.
        for chunk in a4(0, 700).iter().chain(a4(500, 1500).iter()).copied().collect::<Vec<f32>>().chunks(512) {
            tx.send(chunk.to_vec()).unwrap();
        }
        let deadline = std::time::Instant::now() + Duration::from_secs(30);
        while !notes_in_user_data().contains(&9601) {
            assert!(std::time::Instant::now() < deadline, "piece 1's note never arrived");
            std::thread::sleep(Duration::from_millis(20));
        }

        // The player moves on to another exercise without stopping the mic.
        api::init_session(piece_json(9602));
        for chunk in a4(500, 1000).chunks(512) {
            tx.send(chunk.to_vec()).unwrap();
        }
        drop(tx);
        worker.join().unwrap();

        let records: Vec<Notes> = lock(&USER_DATA).clone().unwrap_or_default();
        assert_eq!(records.iter().map(|n| n.note_id).collect::<Vec<_>>(), vec![9602], "{records:?}");
        assert_eq!(records[0].start_time_ms, Some(0.0), "the new piece's clock starts at its own first note");
        *lock(&ACTIVE_PIECE) = None;
        *lock(&USER_DATA) = None;
    }

    #[test]
    fn test_error_message_is_copied_out_cut_to_the_buffer_and_never_overruns() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        audio::clear_status();
        audio::report(audio::AUDIO_ERR_OPEN, "microphone: é busy");
        let mut buf = [0xAAu8; 64];
        let n = unsafe { audio_error_message(buf.as_mut_ptr(), buf.len()) };
        assert_eq!(&buf[..n], "microphone: é busy".as_bytes());
        assert_eq!(buf[n], 0, "NUL-terminated");

        // A buffer too small to hold the message cuts it, on a character boundary.
        let mut small = [0xAAu8; 14];
        let n = unsafe { audio_error_message(small.as_mut_ptr(), small.len()) };
        assert_eq!(std::str::from_utf8(&small[..n]).unwrap(), "microphone: ");
        assert_eq!(small[n], 0);

        assert_eq!(unsafe { audio_error_message(std::ptr::null_mut(), 10) }, 0);
        assert_eq!(unsafe { audio_error_message(buf.as_mut_ptr(), 0) }, 0);
        assert_eq!(audio_status(), audio::AUDIO_ERR_OPEN);
        audio::clear_status();
    }

    #[test]
    fn test_listen_audio_says_why_when_the_microphone_cannot_open() {
        let _serial = audio::TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        audio::clear_status();
        let code = listen_audio();
        if code == audio::AUDIO_OK {
            // A machine with a microphone: nothing to check but a clean stop.
            stop_audio();
            assert!(wait_for_worker(WORKER_TIMEOUT));
            return;
        }
        assert_eq!(audio_status(), code, "the status carries the code listen_audio returned");
        assert!(code < audio::AUDIO_WARN_SILENT_INPUT, "a failure to open is an error, not a warning");
        let mut buf = [0u8; 256];
        let n = unsafe { audio_error_message(buf.as_mut_ptr(), buf.len()) };
        assert!(n > 0, "an error code without a message is no help to the player");
        assert!(lock(&ACTIVE_STREAM).is_none(), "nothing may be left open");
        assert!(wait_for_worker(Duration::from_millis(50)), "and no processing thread started");
        stop_audio(); // stopping when nothing runs is fine
        audio::clear_status();
    }
}

