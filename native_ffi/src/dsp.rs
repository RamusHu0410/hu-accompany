use realfft::{RealFftPlanner, RealToComplex};
use num_complex::Complex;
use std::sync::{Arc, LazyLock, Mutex};

const LEN: usize = 2048;
static FFT_PLANNER: LazyLock<Mutex<RealFftPlanner<f32>>> =
    LazyLock::new(|| Mutex::new(RealFftPlanner::new()));

static FFT: LazyLock<Arc<dyn RealToComplex<f32>>> = LazyLock::new(|| {
    let mut planner = FFT_PLANNER.lock().unwrap();
    planner.plan_fft_foward(1024)
});

pub fn run_fft(input_data: &mut Vec<f32>, output_spectrum: &mut Vec<Complex<f32>>) {
    FFT.process(input_data, output_spectrum).unwrap();
}

pub fn process_dsp(output_spectrum: &Vec<Complex<f32>>) -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    let detected_notes: Vec<f32> = Vec::new();
    let mut max_mag = 0.0;
    let mut max_bin_index = 0;

    for (i, cplx) in output_spectrum.iter().enumerate() {
        if i < 4 { continue; }
        let mag = cplx.norm();
        
        if mag > max_mag {
            max_mag = mag;
            max_bin_index = i;
        }
    }
    if max_mag < 0.1 {
        return Ok(vec![0.0]);
    }
    let detected_hz = (peak_bin_index as f32) * (44100.0 / 1024.0);
    Ok(detected_notes)
}
