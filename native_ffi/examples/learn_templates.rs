//! Learns an instrument's note templates from a calibration recording: every
//! note played alone (e.g. a chromatic scale), with its score.
//!
//! cargo run --release --example learn_templates -- <calibration.wav> <score.json> <out.json> [--instrument Piano]
//!
//! Then run with them: NOTE_TEMPLATES=<out.json> cargo test --release --test real_audio -- --ignored

mod common;

use native_ffi::templates::NoteTemplates;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: learn_templates <calibration.wav> <score.json> <out.json> [--instrument Piano]");
        std::process::exit(2);
    }
    let instrument = common::flag(&args, "--instrument").unwrap_or("Piano");
    let (mono, spec) = common::load_wav_mono(&args[1]);
    let piece = common::load_piece(&args[2], 0.0);
    let templates = NoteTemplates::learn(instrument, &mono, spec.sample_rate, &piece.notes);
    std::fs::write(&args[3], serde_json::to_string_pretty(&templates).unwrap()).unwrap();
    println!("{} templates for {instrument} -> {}", templates.profiles.len(), args[3]);
}
