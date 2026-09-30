//! Real-world audio benchmark: real recordings with note-level ground truth,
//! run through the same pipeline as the mic. No Flutter needed.
//!
//! One-time data fetch (~12 MB):  python3 fixtures/real/fetch_guitarset.py
//! Run:  cargo test --test real_audio -- --ignored --nocapture
//! Held-out clips (never used for tuning): see fixtures/real/fetch_guitarset.py
//!
//! Ignored by default so plain `cargo test` stays fast and offline.

#[allow(dead_code)]
#[path = "../examples/common/mod.rs"]
mod common;

use native_ffi::models::{Notes, PieceData};
use native_ffi::tracker::TIMING_MARGIN_MS;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

// ---- Pass/fail targets (PROVISIONAL: product decisions, tune them) ----
/// Half a semitone: within this, the player hit the right note.
const PITCH_TOLERANCE_CENTS: f64 = 50.0;
/// Share of single-note-line notes we must recognise.
const MIN_SOLO_RECALL: f64 = 0.80;
/// Share of chord notes we must recognise (harder: notes mask each other).
const MIN_CHORD_RECALL: f64 = 0.70;
/// Share of notes we may wrongly accept when the score is a semitone off.
const MAX_SEMITONE_FALSE_ACCEPT: f64 = 0.10;

/// The pipeline uses process-wide globals, so benchmark runs must not overlap.
static PIPELINE: Mutex<()> = Mutex::new(());

fn fixtures() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures")
}

/// (wav, piece json) pairs for one GuitarSet take kind: "solo" or "comp".
/// REAL_AUDIO_DIR points at another clip set, e.g. the held-out one.
fn guitarset_clips(kind: &str) -> Vec<(PathBuf, PathBuf)> {
    let dir = std::env::var("REAL_AUDIO_DIR")
        .ok()
        .filter(|d| !d.is_empty())
        .map(|d| Path::new(env!("CARGO_MANIFEST_DIR")).join(d))
        .unwrap_or_else(|| fixtures().join("real/guitarset"));
    let mut clips: Vec<(PathBuf, PathBuf)> = std::fs::read_dir(&dir)
        .unwrap_or_else(|_| {
            panic!("no real audio in {dir:?}. Run: python3 fixtures/real/fetch_guitarset.py")
        })
        .map(|e| e.unwrap().path())
        .filter(|p| p.to_string_lossy().ends_with(&format!("_{kind}.wav")))
        .map(|wav| (wav.clone(), wav.with_extension("json")))
        .collect();
    clips.sort();
    assert!(!clips.is_empty(), "no *_{kind}.wav clips in {dir:?}");
    clips
}

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

#[derive(Default)]
struct Score {
    notes: usize,
    /// Notes whose detected pitch was within PITCH_TOLERANCE_CENTS of the score.
    recognised: usize,
    /// Notes the detector reported at all (any pitch).
    reported: usize,
    abs_cents: Vec<f64>,
    onset_err_ms: Vec<f64>,
}

impl Score {
    fn rate(&self) -> f64 {
        self.recognised as f64 / self.notes.max(1) as f64
    }
    fn add(&mut self, other: Score) {
        self.notes += other.notes;
        self.recognised += other.recognised;
        self.reported += other.reported;
        self.abs_cents.extend(other.abs_cents);
        self.onset_err_ms.extend(other.onset_err_ms);
    }
}

/// Compares detector output to the score, note by note.
/// Each record is one played note carrying its measured pitch; a note split
/// into several records (fragmented) is judged on their median pitch.
fn score_clip(piece: &PieceData, records: &[Notes]) -> Score {
    let mut s = Score { notes: piece.notes.len(), ..Score::default() };
    for note in &piece.notes {
        let live: Vec<&Notes> = records.iter().filter(|r| r.note_id == note.note_id).collect();
        let Some(pitch) = median(live.iter().map(|r| r.pitch_hz).collect()) else {
            continue;
        };
        s.reported += 1;
        let off = cents(pitch, note.pitch_hz).abs();
        s.abs_cents.push(off);
        if off <= PITCH_TOLERANCE_CENTS {
            s.recognised += 1;
        }
        let first_heard = live.iter().filter_map(|r| r.start_time_ms).fold(f32::MAX, f32::min);
        if let Some(score_start) = note.start_time_ms {
            // Signed: positive = we report the note late. A consistent bias
            // can be corrected with a constant; scatter cannot.
            s.onset_err_ms.push((first_heard - score_start) as f64);
        }
    }
    s
}

/// Keeps only the shifted notes whose (wrong) pitch is NOT actually sounding
/// per the ground truth during the note's listening window. On guitar,
/// earlier notes ring on and melodies step by semitones, so some "wrong" notes
/// are genuinely audible; detecting those is correct, not a false accept.
fn truly_absent_notes(shifted: &PieceData, ground_truth: &PieceData) -> PieceData {
    let mut clean = shifted.clone();
    clean.notes.retain(|wrong| {
        let (Some(start), Some(end)) = (wrong.start_time_ms, wrong.end_time_ms) else {
            return true;
        };
        let (open, close) = (start - TIMING_MARGIN_MS, end + TIMING_MARGIN_MS);
        !ground_truth.notes.iter().any(|played| {
            cents(played.pitch_hz, wrong.pitch_hz).abs() < 50.0
                && played.start_time_ms.is_some_and(|s| s < close)
                && played.end_time_ms.is_some_and(|e| e > open)
        })
    });
    clean
}

/// Same notes, every pitch raised a semitone: what a wrong-note performance
/// looks like from the detector's side.
fn shifted_up_a_semitone(piece: &PieceData) -> PieceData {
    let mut shifted = piece.clone();
    for n in &mut shifted.notes {
        n.pitch_hz *= 2f64.powf(1.0 / 12.0);
    }
    shifted
}

fn run_clip(wav: &Path, piece: &PieceData) -> Vec<Notes> {
    let (mono, spec) = common::load_wav_mono(wav.to_str().unwrap());
    common::run_pipeline(&mono, spec.sample_rate, piece)
}

fn print_row(name: &str, s: &Score) {
    let fmt = |v: Option<f64>, unit: &str| v.map_or("-".into(), |x| format!("{x:.0}{unit}"));
    let fmt_signed = |v: Option<f64>, unit: &str| v.map_or("-".into(), |x| format!("{x:+.0}{unit}"));
    let abs_onsets: Vec<f64> = s.onset_err_ms.iter().map(|x| x.abs()).collect();
    println!(
        "  {:<28} {:>4} notes  recognised {:>5.1}%  reported {:>5.1}%  median |err| {:>9}  onset bias {:>7} (|err| {:>6})",
        name,
        s.notes,
        100.0 * s.rate(),
        100.0 * s.reported as f64 / s.notes.max(1) as f64,
        fmt(median(s.abs_cents.clone()), " cents"),
        fmt_signed(median(s.onset_err_ms.clone()), " ms"),
        fmt(median(abs_onsets), " ms"),
    );
}

/// Runs every clip of `kind`; returns (correct score, semitone-shifted score
/// counting only wrong notes that were truly not played).
fn benchmark(kind: &str) -> (Score, Score) {
    let _serial = PIPELINE.lock().unwrap_or_else(|e| e.into_inner());
    let (mut total, mut shifted_raw, mut shifted_clean) =
        (Score::default(), Score::default(), Score::default());
    println!("\n[{kind}] correct score:");
    for (wav, json) in guitarset_clips(kind) {
        let piece = common::load_piece(json.to_str().unwrap(), 0.0);
        let s = score_clip(&piece, &run_clip(&wav, &piece));
        print_row(&wav.file_stem().unwrap().to_string_lossy(), &s);
        total.add(s);

        // The detector gets the whole wrong score (realistic); only the
        // scoring skips wrong pitches that were genuinely audible.
        let wrong = shifted_up_a_semitone(&piece);
        let records = run_clip(&wav, &wrong);
        shifted_raw.add(score_clip(&wrong, &records));
        shifted_clean.add(score_clip(&truly_absent_notes(&wrong, &piece), &records));
    }
    print_row("TOTAL", &total);
    println!("[{kind}] score shifted up a semitone (should NOT be recognised):");
    print_row("raw (incl. really-audible)", &shifted_raw);
    print_row("TOTAL (false accepts)", &shifted_clean);
    (total, shifted_clean)
}

#[test]
#[ignore = "needs fixtures/real data; run with --ignored"]
fn real_solo_guitar_notes_are_recognised_and_wrong_notes_rejected() {
    let (correct, shifted) = benchmark("solo");
    assert!(
        correct.rate() >= MIN_SOLO_RECALL,
        "solo recall {:.1}% < {:.0}%",
        100.0 * correct.rate(),
        100.0 * MIN_SOLO_RECALL
    );
    assert!(
        shifted.rate() <= MAX_SEMITONE_FALSE_ACCEPT,
        "accepted {:.1}% of semitone-wrong notes (max {:.0}%)",
        100.0 * shifted.rate(),
        100.0 * MAX_SEMITONE_FALSE_ACCEPT
    );
}

#[test]
#[ignore = "needs fixtures/real data; run with --ignored"]
fn real_guitar_chords_are_recognised_and_wrong_notes_rejected() {
    let (correct, shifted) = benchmark("comp");
    assert!(
        correct.rate() >= MIN_CHORD_RECALL,
        "chord recall {:.1}% < {:.0}%",
        100.0 * correct.rate(),
        100.0 * MIN_CHORD_RECALL
    );
    assert!(
        shifted.rate() <= MAX_SEMITONE_FALSE_ACCEPT,
        "accepted {:.1}% of semitone-wrong notes (max {:.0}%)",
        100.0 * shifted.rate(),
        100.0 * MAX_SEMITONE_FALSE_ACCEPT
    );
}

/// Recordings of a room where nobody played (talking, TV, knocks).
/// Drop your own takes in as fixtures/real/silent_room_*.wav, recorded with
/// `live fixtures/three_notes.json --offset-ms 2000 --save ...`.
#[test]
#[ignore = "needs fixtures/real data; run with --ignored"]
fn silent_room_recordings_detect_no_notes() {
    let _serial = PIPELINE.lock().unwrap_or_else(|e| e.into_inner());
    let mut takes: Vec<PathBuf> = std::fs::read_dir(fixtures().join("real"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| {
            let name = p.file_name().unwrap().to_string_lossy();
            name.starts_with("silent_room") && name.ends_with(".wav")
        })
        .collect();
    takes.sort();
    assert!(!takes.is_empty(), "no fixtures/real/silent_room_*.wav recordings");

    let piece = common::load_piece(fixtures().join("three_notes.json").to_str().unwrap(), 2000.0);
    let mut failures = Vec::new();
    println!("\n[silent room] expected: 0 notes reported");
    for take in &takes {
        let s = score_clip(&piece, &run_clip(take, &piece));
        print_row(&take.file_stem().unwrap().to_string_lossy(), &s);
        if s.reported > 0 {
            failures.push(format!("{:?}: {} notes reported", take.file_name().unwrap(), s.reported));
        }
    }
    assert!(failures.is_empty(), "detections in an empty room: {failures:?}");
}
