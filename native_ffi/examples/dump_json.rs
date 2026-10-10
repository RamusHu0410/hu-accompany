//! Replays a WAV recording through the real detection pipeline and writes what
//! Rust hands to Dart as JSON: the same array of `Notes` that `get_user_data()`
//! returns, so it can be checked against the Python backend's request format.
//!
//! cargo run --release --example dump_json -- <audio.wav> <piece.json> [--offset-ms N] [--out <file>]
//!
//! Without --out the JSON goes to stdout. A recording in which nothing is
//! detected writes `[]`, which the backend accepts as silence.

#[allow(dead_code)] // the report printer is only used by `replay`
mod common;

use native_ffi::models::Notes;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: dump_json <audio.wav> <piece.json> [--offset-ms N] [--out <file>]");
        std::process::exit(2);
    }
    let offset_ms: f32 = common::flag(&args, "--offset-ms")
        .map(|v| v.parse().expect("--offset-ms must be a number"))
        .unwrap_or(0.0);

    let (mono, spec) = common::load_wav_mono(&args[1]);
    let piece = common::load_piece(&args[2], offset_ms);
    let records = common::run_pipeline(&mono, spec.sample_rate, &piece);

    let json = serde_json::to_string_pretty(&records).expect("Notes always serialize");
    // Guard: what we write must read back as the same `Notes` the app receives.
    let reread: Vec<Notes> = serde_json::from_str(&json).expect("dump does not read back as Notes");
    assert_eq!(reread.len(), records.len());

    match common::flag(&args, "--out") {
        Some(path) => {
            if let Some(dir) = std::path::Path::new(path).parent() {
                std::fs::create_dir_all(dir).unwrap_or_else(|e| panic!("could not create {dir:?}: {e}"));
            }
            std::fs::write(path, format!("{json}\n")).unwrap_or_else(|e| panic!("could not write {path}: {e}"));
            eprintln!("wrote {} note(s) to {path}", records.len());
        }
        None => println!("{json}"),
    }
}
