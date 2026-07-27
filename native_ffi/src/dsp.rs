use crate::models::PieceData;
use num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::sync::{Arc, LazyLock, Mutex};
use crate::ACTIVE_PIECE;
use crate::USER_DATA;
use crate::models::Notes;
use std::time::Instant;

const LEN: usize = 2048;
const FFT_WINDOWSIZE: u32 = 1024;
const SAMPLE_RATE: u32 = 44100;
static FFT_PLANNER: LazyLock<Mutex<RealFftPlanner<f32>>> =
    LazyLock::new(|| Mutex::new(RealFftPlanner::new()));

static FFT: LazyLock<Arc<dyn RealToComplex<f32>>> = LazyLock::new(|| {
    let mut planner = FFT_PLANNER.lock().unwrap();
    planner.plan_fft_foward(FFT_WINDOWSIZE)
});

pub fn get_current_targets(curr_ms: f32, piece_data: &PieceData) -> Vec<f32> {
    let margin_err = 85.0;
    
    piece_data.notes
        .iter()
        .filter(|&note| {
            let soft_start = note.start_time_ms.saturating_sub(margin_err);
            let soft_end = note.end_time_ms.saturating_add(margin_err);
            
            curr_ms >= soft_start && curr_ms <= soft_end
        })
        .map(|note| note.pitch_hz)
        .collect() 
}

pub fn run_fft(input_data: &mut Vec<f32>, output_spectrum: &mut Vec<Complex<f32>>) {
    FFT.process(input_data, output_spectrum).unwrap();
}

pub fn process_dsp(
    output_spectrum: &Vec<Complex<f32>>,
    target_notes: &Vec<f32>
) -> Result<(), Box<dyn std::error::Error>> {
    const THRESHOLD: f32 = 5.0;
    let detected_notes: Vec<f32> = Vec::new();
    let mut max_mag = 0.0;
    let mut max_bin_index = 0;
    let mut user_data = USER_DATA.lock().unwrap();
    *user_data = None;

    for note in target_notes {
        let target_bin = ((note * FFT_WINDOWSIZE) / SAMPLE_RATE).round();
        let mag_left = output_spectrum[target_bin - 1].norm();
        let mag_center = output_spectrum[target_bin].norm();
        let mag_right = output_spectrum[target_bin + 1].norm();
        let user_note = mag_left.max(mag_center).max(mag_right);
        detected_notes.push(user_note);
    }
    *user_data = Some(Vec::new()); 
    for note in detected_notes {
        let note_data = None; // * Problem: order of recieved notes is random, hard to align with
                              // original piece data
        *user_data.push(note_data);
    }
    Ok(())
}
