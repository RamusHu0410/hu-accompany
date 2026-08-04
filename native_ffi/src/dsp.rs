use crate::models::Notes;
use crate::models::PieceData;
use crate::{ACTIVE_PIECE, USER_DATA};
use num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::sync::{Arc, LazyLock, Mutex};

const LEN: usize = 2048;
const FFT_WINDOWSIZE: u32 = 1024;
const SAMPLE_RATE: u32 = 44100;
static FFT_PLANNER: LazyLock<Mutex<RealFftPlanner<f32>>> =
    LazyLock::new(|| Mutex::new(RealFftPlanner::new()));

static FFT: LazyLock<Arc<dyn RealToComplex<f32>>> = LazyLock::new(|| {
    let mut planner = FFT_PLANNER.lock().unwrap();
    planner.plan_fft_foward(FFT_WINDOWSIZE)
});

pub fn get_current_targets(curr_ms: f32, piece_data: &PieceData) -> Vec<Notes> {
    let margin_err = 85.0;

    piece_data
        .notes
        .iter()
        .filter(|&note| {
            let soft_start = note.start_time_ms.saturating_sub(margin_err);
            let soft_end = note.end_time_ms.saturating_add(margin_err);

            curr_ms >= soft_start && curr_ms <= soft_end
        })
        .collect()
}

pub fn run_fft(input_data: &mut Vec<f32>, output_spectrum: &mut Vec<Complex<f32>>) {
    FFT.process(input_data, output_spectrum).unwrap();
}

pub fn process_dsp(
    output_spectrum: &Vec<Complex<f32>>,
    target_notes: &Vec<Notes>,
    curr_ms: f32,
    note_start_ms: &mut Option<f32>,
) -> Result<(), Box<dyn std::error::Error>> {
    const THRESHOLD: f32 = 5.0;

    let mut user_data = USER_DATA.lock().unwrap();
    // Initialize or re-assign user_data vector
    let notes_vec = user_data.get_or_insert_with(Vec::new);

    for note in target_notes {
        let target_bin = ((note.pitch_hz * FFT_WINDOWSIZE) / SAMPLE_RATE).round() as usize;

        if target_bin > 0 && target_bin < output_spectrum.len() - 1 {
            let alpha = output_spectrum[target_bin - 1].norm(); // mag_left
            let beta = output_spectrum[target_bin].norm(); // mag_center
            let gamma = output_spectrum[target_bin + 1].norm(); // mag_right

            // Peak volume in the neighborhood
            let max_magnitude = alpha.max(beta).max(gamma);

            // Check if user is actually playing above volume threshold
            if max_magnitude >= THRESHOLD {
                // 1. Lock start_ms on the FIRST frame played (or keep original start_ms)
                let start = *note_start_ms.get_or_insert(curr_ms);

                // 2. Real-time active duration so far:
                let live_duration = curr_ms - start;

                // Parabolic Interpolation for exact pitch
                let denominator = alpha - (2.0 * beta) + gamma;
                let bin_offset = if denominator.abs() > 1e-5 {
                    0.5 * (alpha - gamma) / denominator
                } else {
                    0.0
                };

                let exact_bin = (target_bin as f32) + bin_offset;
                let detected_hz = (exact_bin * SAMPLE_RATE) / FFT_WINDOWSIZE;

                // Push the active note with start_ms and current duration
                notes_vec.push(Notes {
                    note_id: note.note_id,
                    pitch_hz: detected_hz,
                    vibrato_depth: None,
                    pedal_action: None,
                    has_accent: None,
                    markings: None,
                    start_time_ms: Some(start),
                    end_time_ms: None, // Still playing, so end_ms is None!
                    duration_ms: Some(live_duration),
                });
            } else {
                // Volume dropped below THRESHOLD -> Note stopped playing
                if let Some(start) = note_start_ms.take() {
                    let end = curr_ms;
                    let final_duration = end - start;

                    // Push final note completion state
                    notes_vec.push(Notes {
                        note_id: note.note_id,
                        pitch_hz: note.pitch_hz,
                        vibrato_depth: None,
                        pedal_action: None,
                        has_accent: None,
                        markings: None,
                        start_time_ms: Some(start),
                        end_time_ms: Some(end),
                        duration_ms: Some(final_duration),
                    });
                }
            }
        }
    }

    Ok(())
}
