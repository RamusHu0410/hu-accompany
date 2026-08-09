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

pub static FFT: LazyLock<Arc<dyn RealToComplex<f32>>> = LazyLock::new(|| {
    let mut planner = FFT_PLANNER.lock().unwrap();
    planner.plan_fft_forward(FFT_WINDOWSIZE as usize)
});

pub fn get_current_targets(curr_ms: f32, piece_data: &PieceData) -> Vec<Notes> {
    let margin_err = 85.0;

    piece_data
        .notes
        .clone()
        .into_iter() // Note: into_iter(), not iter_into()
        .filter(|note| {
            // 1. Extract values outside the condition evaluation
            let (soft_start, soft_end) = if let Some(start) = note.start_time_ms {
                let s_start = (start - margin_err).max(0.0);
                let s_end = note.end_time_ms.map(|e| e + margin_err).unwrap_or(s_start);
                (s_start, s_end)
            } else {
                return false; // Skip notes with no start time
            };

            // 2. Boolean check completely outside the `if let`
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
        let target_bin = ((note.pitch_hz * (FFT_WINDOWSIZE as f64)) / (SAMPLE_RATE as f64)).round() as usize;

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

                let exact_bin = (target_bin as f64) + (bin_offset as f64);
                let detected_hz = ((exact_bin * (SAMPLE_RATE as f64)) / (FFT_WINDOWSIZE as f64) as f64);

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

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    // Helper to generate a pure sine wave buffer
    fn generate_sine_wave(freq_hz: f32, sample_rate: f32, num_samples: usize) -> Vec<f32> {
        (0..num_samples)
            .map(|i| (2.0 * PI * freq_hz * (i as f32) / sample_rate).sin())
            .collect()
    }

    #[test]
    fn test_c4_pitch_detection() {
        let sample_rate = 44100.0;
        let c4_wave = generate_sine_wave(261.63, sample_rate, 1024);

        let mut input_buffer = c4_wave.clone();
        let mut output_spectrum = crate::dsp::FFT.make_output_vec();

        // Run FFT
        crate::dsp::run_fft(&mut input_buffer, &mut output_spectrum);

        // Verify target bin calculation / interpolation
        let target_notes = vec![Notes {
            note_id: 1,
            pitch_hz: 261.63,
            vibrato_depth: None,
            pedal_action: None,
            has_accent: None,
            markings: None,
            start_time_ms: None,
            end_time_ms: None,
            duration_ms: None,
        }];

        let mut note_start_ms = None;
        let result = process_dsp(&output_spectrum, &target_notes, 100.0, &mut note_start_ms);

        assert!(result.is_ok());
        assert!(
            note_start_ms.is_some(),
            "Note should cross volume threshold!"
        );
    }
}
