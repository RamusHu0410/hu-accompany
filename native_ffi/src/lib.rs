mod frb_generated; /* AUTO INJECTED BY flutter_rust_bridge. This line may not be accurate, and you can change it according to your needs. */
// Modules
pub mod audio;
pub mod dsp;
pub mod models;
pub mod run_onnx;

// Crates
use crate::frb_generated::StreamSink;
use flutter_rust_bridge::frb;
use once_cell::sync::Lazy;
use std::sync::RwLock;
use std::sync::{LazyLock, Mutex};

// Custom Defined types
use models::{Notes, PieceData, SendStream};

static NOTES_SINK: RwLock<Option<StreamSink<Vec<Notes>>>> = RwLock::new(None);
static ACTIVE_STREAM: Lazy<Mutex<Option<SendStream>>> = Lazy::new(|| Mutex::new(None));
pub static ACTIVE_PIECE: LazyLock<Mutex<Option<PieceData>>> = LazyLock::new(|| Mutex::new(None));
pub static USER_DATA: LazyLock<Mutex<Option<Vec<Notes>>>> = LazyLock::new(|| Mutex::new(None));

#[frb(ignore)]
#[unsafe(no_mangle)]
pub extern "C" fn listen_audio() {
    let mut stream_guard = ACTIVE_STREAM.lock().unwrap();
    if stream_guard.is_some() {
        return;
    }
    let (tx, rx) = std::sync::mpsc::channel::<Vec<f32>>();
    let _my_live_stream = audio::create_stream(tx);
    std::thread::spawn(move || {
        audio::start_processing_loop(rx);
    });
    if let Ok(stream) = _my_live_stream {
        *stream_guard = Some(SendStream(stream));
    }
}

#[frb(ignore)]
#[unsafe(no_mangle)]
pub extern "C" fn stop_audio() {
    let mut stream_guard = ACTIVE_STREAM.lock().unwrap();
    if let Some(stream) = stream_guard.take() {
        // Dropping the stream object turns off the microphone hardware
        std::mem::drop(stream);
    }
}

mod api {
    use super::*;
    use crate::models::Notes;
    pub fn init_session(json_data: String) {
        let piece_data: PieceData = serde_json::from_str(&json_data).unwrap();

        let mut active_slot = ACTIVE_PIECE.lock().unwrap();
        *active_slot = Some(piece_data);
    }

    // FRB handles returning standard Strings and frees the memory safely.
    pub fn get_user_data() -> String {
        let user_data = USER_DATA.lock().unwrap();
        serde_json::to_string(&*user_data).unwrap_or_else(|_| "{}".to_string())
    }
    pub fn notes_stream(s: StreamSink<Vec<Notes>>) {
        *NOTES_SINK.write().unwrap() = Some(s);
    }

    /// TEST ONLY. Pushes an already-detected phrase straight into the
    /// notes_stream sink, so the Dart side receives it exactly as if the
    /// microphone and pitch detection had produced it.
    ///
    /// This exists so the Rust -> Dart -> Python -> Dart round trip can be
    /// exercised without working audio capture. It deliberately does not
    /// touch `listen_audio`, `stop_audio` or any part of the real capture
    /// path -- it only borrows the same sink those would ultimately feed.
    ///
    /// `json_data` is the sample payload used by the Python backend (see
    /// backend/feedback_generator/sample_data/phrase_imperfect.json); the
    /// `user_notes` array is what gets injected. Fields the real `Notes`
    /// struct carries but that sample omits (`is_end` and the optional
    /// expressive ones) default rather than failing to parse.
    ///
    /// Returns a status string instead of panicking, because an unwrap here
    /// would abort across the FFI boundary and take the app down.
    pub fn inject_test_phrase(json_data: String) -> String {
        use serde::Deserialize;

        #[derive(Deserialize)]
        struct TestNote {
            note_id: u64,
            pitch_hz: f64,
            #[serde(default)]
            start_time_ms: Option<f32>,
            #[serde(default)]
            end_time_ms: Option<f32>,
            #[serde(default)]
            duration_ms: Option<f32>,
            #[serde(default)]
            has_accent: Option<bool>,
        }

        #[derive(Deserialize)]
        struct TestPayload {
            user_notes: Vec<TestNote>,
        }

        let payload: TestPayload = match serde_json::from_str(&json_data) {
            Ok(parsed) => parsed,
            Err(e) => return format!("inject_test_phrase: bad JSON -- {e}"),
        };

        if payload.user_notes.is_empty() {
            return "inject_test_phrase: user_notes was empty".to_string();
        }

        let last = payload.user_notes.len() - 1;
        let notes: Vec<Notes> = payload
            .user_notes
            .into_iter()
            .enumerate()
            .map(|(i, n)| Notes {
                note_id: n.note_id,
                pitch_hz: n.pitch_hz,
                start_time_ms: n.start_time_ms,
                end_time_ms: n.end_time_ms,
                duration_ms: n.duration_ms,
                // The real detector marks the closing note of a phrase, so
                // the injected phrase terminates the same way.
                is_end: i == last,
                vibrato_depth: None,
                pedal_action: None,
                has_accent: n.has_accent,
                markings: None,
            })
            .collect();

        let count = notes.len();
        match NOTES_SINK.read() {
            Ok(guard) => match guard.as_ref() {
                Some(sink) => {
                    let _ = sink.add(notes);
                    format!("inject_test_phrase: sent {count} note(s)")
                }
                None => "inject_test_phrase: no listener -- call notesStream() first"
                    .to_string(),
            },
            Err(_) => "inject_test_phrase: notes sink lock poisoned".to_string(),
        }
    }
}
