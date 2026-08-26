use crate::{ACTIVE_PIECE, USER_DATA};
use crate::models::PieceData;
use cpal::Stream;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::mpsc::Receiver;
use std::sync::mpsc::Sender;

static RMS_THRESHOLD: Option<f32> = None;
const FFT_WINDOWSIZE: u32 = 1024;
const SAMPLE_RATE: u32 = 44100;
const BUFF_DURATION: f32 = (128.0f32 / (SAMPLE_RATE as f32)) * 1000.0f32;

pub fn create_stream(tx: Sender<Vec<f32>>) -> Result<Stream, Box<dyn std::error::Error>> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .expect("No Input Devices Found!!");
    let config = device.default_input_config()?;
    let sample_rate = config.sample_rate().0;
    let err_fn = |err| eprintln!("An error occurred on the audio stream: {}", err);
    let sample_format = config.sample_format();
    let config: cpal::StreamConfig = config.into();
    let stream = match sample_format {
        cpal::SampleFormat::F32 => device.build_input_stream(
            &config,
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                let _ = tx.send(data.to_vec());
            },
            err_fn,
            None,
        )?,
        _ => panic!("Unsupported sample format! (Expected f32)"),
    };
    stream.play()?;
    Ok(stream)
}

pub fn start_processing_loop(rx: Receiver<Vec<f32>>) {
    let mut audio_vault: Vec<f32> = Vec::new();
    let mut input_data_buffer = vec![0.0f32; 1024];
    let mut output_spectrum = crate::dsp::FFT.make_output_vec();
    let mut processed_windows: u64 = 0;
    let mut note_start_ms: Option<f32> = None;

    // This loop runs when data is recieved from rx
    while let Ok(chunk) = rx.recv() {
        audio_vault.extend_from_slice(&chunk);

        while audio_vault.len() >= 1024 {
            let current_ms: f32 = BUFF_DURATION * (processed_windows as f32);
            let processing_data = &audio_vault[0..1024];
            let rms: f32 = (processing_data
            .iter()
            .map(|&x| x * x)    // 1. Square every sample
            .sum::<f32>()       // 2. Add them all together
            / 1024.0) // 3. Divide by 1024 (Mean)
                .sqrt();
            if rms <= 0.0075 {
                audio_vault.drain(0..128);
                processed_windows += 1;
                continue;
            }

            input_data_buffer.copy_from_slice(&audio_vault[0..1024]);
            crate::dsp::run_fft(&mut input_data_buffer, &mut output_spectrum);

            if let Some(ref piece) = *ACTIVE_PIECE.lock().unwrap() {
                match &piece.curr_phase {
                    0 | 1 => {
                        let target_notes = crate::dsp::get_current_targets(current_ms, piece);
                        let _ = crate::dsp::process_dsp(&output_spectrum, 
                            &target_notes, 
                            current_ms, 
                            &mut note_start_ms
                        );
                    }
                    2 | 3 => {}
                    _ => {}
                }
            }
            audio_vault.drain(0..128);
            processed_windows += 1;
        }
    }
}
