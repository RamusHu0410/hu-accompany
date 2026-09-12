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
}
