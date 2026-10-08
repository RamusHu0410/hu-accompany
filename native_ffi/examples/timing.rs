//! Measures how far reported note starts and ends are from the score, over a
//! directory of clips (WAV + PieceData JSON, e.g. fixtures/real/maestro_heldout).
//!
//! cargo run --release --example timing -- <dir> [--lead-ms N] [--evidence dsp|neural] [--no-anchor]
//!
//! `--lead-ms N` puts N ms of silence in front of the audio without moving the
//! score: what a microphone opened N ms before the player starts looks like.
//! `--no-anchor` runs the score's clock from sample 0 instead of the first note.
//! Errors are signed (positive = reported late) and in the score's own clock.

mod common;

use native_ffi::models::Notes;

fn percentile(sorted: &[f64], p: f64) -> f64 {
    sorted[((sorted.len() - 1) as f64 * p).round() as usize]
}

fn summary(label: &str, mut v: Vec<f64>, margin: f64) {
    if v.is_empty() {
        println!("  {label:<6} no notes");
        return;
    }
    v.sort_by(f64::total_cmp);
    let within = v.iter().filter(|e| e.abs() <= margin).count();
    println!(
        "  {label:<6} median {:+6.0} ms   p10 {:+6.0}   p90 {:+6.0}   within ±{margin:.0} ms: {:>5.1}%",
        percentile(&v, 0.5),
        percentile(&v, 0.1),
        percentile(&v, 0.9),
        100.0 * within as f64 / v.len() as f64
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let dir = args.get(1).expect("usage: timing <dir> [--lead-ms N] [--evidence dsp|neural] [--no-anchor]");
    let lead_ms: f32 = common::flag(&args, "--lead-ms").map_or(0.0, |v| v.parse().expect("--lead-ms is a number"));
    if args.iter().any(|a| a == "--no-anchor") {
        native_ffi::ANCHOR_CLOCK.store(false, std::sync::atomic::Ordering::Relaxed);
    }
    // common::run_pipeline reads EVIDENCE.
    if let Some(e) = common::flag(&args, "--evidence") {
        unsafe { std::env::set_var("EVIDENCE", e) };
    }

    let mut wavs: Vec<_> = std::fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("{dir}: {e}"))
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "wav"))
        .collect();
    wavs.sort();

    let (mut onsets, mut offsets, mut durations) = (Vec::new(), Vec::new(), Vec::new());
    let (mut notes_total, mut found_total, mut fragmented) = (0usize, 0usize, 0usize);
    for wav in &wavs {
        let (mut mono, spec) = common::load_wav_mono(wav.to_str().unwrap());
        let lead = (lead_ms / 1000.0 * spec.sample_rate as f32) as usize;
        mono.splice(0..0, std::iter::repeat_n(0.0, lead));
        let piece = common::load_piece(wav.with_extension("json").to_str().unwrap(), 0.0);
        let records: Vec<Notes> = common::run_pipeline(&mono, spec.sample_rate, &piece);

        let (mut on, mut off, mut dur, mut found) = (Vec::new(), Vec::new(), Vec::new(), 0usize);
        for note in &piece.notes {
            let mine: Vec<&Notes> = records.iter().filter(|r| r.note_id == note.note_id && r.end_time_ms.is_some()).collect();
            if mine.is_empty() {
                continue;
            }
            found += 1;
            if mine.len() > 1 {
                fragmented += 1;
            }
            let start = mine.iter().filter_map(|r| r.start_time_ms).fold(f32::MAX, f32::min);
            let end = mine.iter().filter_map(|r| r.end_time_ms).fold(f32::MIN, f32::max);
            on.push((start - note.start_time_ms.unwrap()) as f64);
            off.push((end - note.end_time_ms.unwrap()) as f64);
            dur.push(((end - start) - (note.end_time_ms.unwrap() - note.start_time_ms.unwrap())) as f64);
        }
        println!("{}: found {found}/{} notes", wav.file_name().unwrap().to_string_lossy(), piece.notes.len());
        notes_total += piece.notes.len();
        found_total += found;
        onsets.extend(on);
        offsets.extend(off);
        durations.extend(dur);
    }
    println!(
        "\nALL: found {found_total}/{notes_total} notes ({:.1}%), {fragmented} split into several records, lead {lead_ms} ms",
        100.0 * found_total as f64 / notes_total.max(1) as f64
    );
    let early = offsets.iter().filter(|&&e| e < -85.0).count();
    println!("  {early} notes ended more than 85 ms before the score says");
    summary("onset", onsets, 85.0);
    summary("offset", offsets, 85.0);
    // The backend's duration finding starts at 15% off the written length.
    summary("length", durations, 85.0);
}
