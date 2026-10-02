//! Shared helpers for the `replay` and `live` harnesses and tests/real_audio.rs.

use native_ffi::audio::{downmix_to_mono, start_processing_loop};
use native_ffi::models::{Notes, PieceData};
use native_ffi::{ACTIVE_PIECE, USER_DATA};

const CHUNK: usize = 512; // typical CoreAudio callback size

/// Reads any WAV (16/24/32-bit int or 32-bit float, any channel count) and
/// returns mono samples in [-1.0, 1.0] (the range cpal delivers) + the sample rate.
pub fn load_wav_mono(path: &str) -> (Vec<f32>, hound::WavSpec) {
    let mut reader =
        hound::WavReader::open(path).unwrap_or_else(|e| panic!("could not open WAV {path}: {e}"));
    let spec = reader.spec();
    let interleaved: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().map(Result::unwrap).collect(),
        hound::SampleFormat::Int => {
            let full_scale = (1i64 << (spec.bits_per_sample - 1)) as f32;
            reader
                .samples::<i32>()
                .map(|s| s.unwrap() as f32 / full_scale)
                .collect()
        }
    };
    (downmix_to_mono(&interleaved, spec.channels as usize), spec)
}

/// Runs mono samples through the real start_processing_loop, in mic-sized
/// chunks, and returns every record the detector produced.
/// Uses the ACTIVE_PIECE / USER_DATA globals, so callers must not overlap.
pub fn run_pipeline(mono: &[f32], sample_rate: u32, piece: &PieceData) -> Vec<Notes> {
    // NOTE_TEMPLATES=path/to/templates.json: run calibrated (see learn_templates).
    *native_ffi::NOTE_TEMPLATES.lock().unwrap() = std::env::var("NOTE_TEMPLATES").ok().filter(|p| !p.is_empty()).map(|p| {
        serde_json::from_str(&std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("NOTE_TEMPLATES {p}: {e}")))
            .unwrap_or_else(|e| panic!("NOTE_TEMPLATES {p}: {e}"))
    });
    // EVIDENCE=dsp: compare against the DSP-only pipeline.
    let neural = std::env::var("EVIDENCE").map_or(true, |v| v != "dsp");
    native_ffi::USE_NEURAL.store(neural, std::sync::atomic::Ordering::Relaxed);
    *USER_DATA.lock().unwrap() = None;
    *ACTIVE_PIECE.lock().unwrap() = Some(piece.clone());

    let (tx, rx) = std::sync::mpsc::channel();
    let worker = std::thread::spawn(move || start_processing_loop(rx, sample_rate));
    for chunk in mono.chunks(CHUNK) {
        tx.send(chunk.to_vec()).unwrap();
    }
    drop(tx); // closing the channel ends the processing loop
    worker.join().expect("processing loop panicked");

    *ACTIVE_PIECE.lock().unwrap() = None;
    USER_DATA.lock().unwrap().take().unwrap_or_default()
}

/// Minimal flag parser: returns the value after `--name`, if present.
pub fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1))
        .map(|s| s.as_str())
}

/// Loads a piece and shifts every note by `offset_ms`.
/// Real recordings start with some silence before the first note, but the
/// detector's clock starts at the first sample, so the score must be shifted
/// to line up (there is no automatic alignment yet).
pub fn load_piece(path: &str, offset_ms: f32) -> PieceData {
    let json = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("could not read piece file {path}: {e}"));
    let mut piece: PieceData =
        serde_json::from_str(&json).unwrap_or_else(|e| panic!("invalid piece JSON in {path}: {e}"));
    for note in &mut piece.notes {
        note.start_time_ms = note.start_time_ms.map(|t| t + offset_ms);
        note.end_time_ms = note.end_time_ms.map(|t| t + offset_ms);
    }
    piece
}

/// Distance between two pitches in cents (100 cents = 1 semitone).
fn cents(detected_hz: f64, target_hz: f64) -> f64 {
    1200.0 * (detected_hz / target_hz).log2()
}

fn median(mut v: Vec<f64>) -> Option<f64> {
    if v.is_empty() {
        return None;
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    Some(v[v.len() / 2])
}

/// Prints one row per score note comparing it with what the detector produced.
///
/// `records` is the detector output: one record per played note, carrying the
/// measured pitch. Several records for one score note = the note was split.
pub fn print_report(piece: &PieceData, records: &[Notes]) {
    println!(
        "\n{:>4}  {:>8}  {:>15}  {:<14}  {:>15}  {:>9}  {:>7}",
        "id", "target", "score ms", "status", "played ms", "median Hz", "cents"
    );
    let (mut hits, mut fragmented, mut missed) = (0, 0, 0);

    for note in &piece.notes {
        let closed: Vec<&Notes> = records.iter().filter(|r| r.note_id == note.note_id).collect();
        let live_pitch = median(closed.iter().map(|r| r.pitch_hz).collect());

        let status = match closed.len() {
            0 => "MISSED".to_string(),
            1 => "HIT".to_string(),
            n => format!("FRAGMENTED({n})"),
        };
        match closed.len() {
            0 => missed += 1,
            1 => hits += 1,
            _ => fragmented += 1,
        }

        let score_ms = format!(
            "{:.0}-{:.0}",
            note.start_time_ms.unwrap_or(f32::NAN),
            note.end_time_ms.unwrap_or(f32::NAN)
        );
        let played_ms = match (closed.first(), closed.last()) {
            (Some(first), Some(last)) => format!(
                "{:.0}-{:.0}",
                first.start_time_ms.unwrap_or(f32::NAN),
                last.end_time_ms.unwrap_or(f32::NAN)
            ),
            _ => "-".to_string(),
        };
        let (median_hz, cents_off) = match live_pitch {
            Some(hz) => (format!("{hz:.1}"), format!("{:+.0}", cents(hz, note.pitch_hz))),
            None => ("-".to_string(), "-".to_string()),
        };

        println!(
            "{:>4}  {:>8.1}  {:>15}  {:<14}  {:>15}  {:>9}  {:>7}",
            note.note_id, note.pitch_hz, score_ms, status, played_ms, median_hz, cents_off
        );
    }

    println!(
        "\n{} notes: {hits} hit, {fragmented} fragmented, {missed} missed/open  ({} raw records)",
        piece.notes.len(),
        records.len()
    );
}
