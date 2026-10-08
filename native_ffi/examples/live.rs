//! Listens to the real microphone and reports what the detector heard.
//!
//! cargo run --example live -- <piece.json> [--seconds N] [--save take.wav] [--offset-ms N]
//!
//! The score's clock starts at your first note of the piece, as in the app.
//! `--save` writes exactly what
//! the processing loop received (mono, device sample rate), so any take can be
//! replayed later with `cargo run --example replay -- take.wav <piece.json>`.

mod common;

use native_ffi::audio::{start_processing_loop, Capture};
use native_ffi::{ACTIVE_PIECE, USER_DATA};
use std::time::Duration;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: live <piece.json> [--seconds N] [--save take.wav] [--offset-ms N]");
        std::process::exit(2);
    }
    let seconds: u64 = common::flag(&args, "--seconds")
        .map(|v| v.parse().expect("--seconds must be a whole number"))
        .unwrap_or(10);
    let offset_ms: f32 = common::flag(&args, "--offset-ms")
        .map(|v| v.parse().expect("--offset-ms must be a number"))
        .unwrap_or(0.0);
    let save_path = common::flag(&args, "--save").map(str::to_string);

    let piece = common::load_piece(&args[1], offset_ms);
    *USER_DATA.lock().unwrap() = None;
    *ACTIVE_PIECE.lock().unwrap() = Some(piece.clone());

    // mic -> tee thread (optionally saves WAV) -> processing loop
    let Capture { stream, sample_rate, chunks: mic_rx, .. } = Capture::open().unwrap_or_else(|e| {
        eprintln!("could not open the microphone: {e}");
        std::process::exit(1);
    });
    let (dsp_tx, dsp_rx) = std::sync::mpsc::channel::<Vec<f32>>();
    let worker = std::thread::spawn(move || start_processing_loop(dsp_rx, sample_rate));

    let tee = std::thread::spawn(move || {
        let mut writer = save_path.as_ref().map(|path| {
            let spec = hound::WavSpec {
                channels: 1,
                sample_rate,
                bits_per_sample: 32,
                sample_format: hound::SampleFormat::Float,
            };
            hound::WavWriter::create(path, spec).expect("could not create WAV file")
        });
        let (mut total, mut peak) = (0usize, 0.0f32);
        while let Ok(chunk) = mic_rx.recv() {
            if let Some(w) = writer.as_mut() {
                for &s in &chunk {
                    w.write_sample(s).unwrap();
                }
            }
            total += chunk.len();
            peak = chunk.iter().fold(peak, |p, s| p.max(s.abs()));
            if dsp_tx.send(chunk).is_err() {
                break;
            }
        }
        if let Some(w) = writer {
            w.finalize().unwrap();
        }
        (total, peak, save_path)
    });

    println!("Mic open at {sample_rate} Hz. Play now — recording for {seconds} s...");
    std::thread::sleep(Duration::from_secs(seconds));
    drop(stream); // stops the mic; channels close and both threads finish

    let (total, peak, saved) = tee.join().unwrap();
    worker.join().expect("processing loop panicked");
    println!("Captured {:.1} s of audio, peak level {peak:.3}", total as f32 / sample_rate as f32);
    if peak < 1e-4 {
        eprintln!(
            "WARNING: the mic delivered silence. On macOS, allow your terminal app under \
             System Settings > Privacy & Security > Microphone, then re-run."
        );
    }
    if let Some(path) = saved {
        println!("Saved take to {path} (replay with: cargo run --example replay -- {path} {})", args[1]);
    }

    let records = USER_DATA.lock().unwrap().take().unwrap_or_default();
    common::print_report(&piece, &records);
}
