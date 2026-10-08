//! Replays a recording at live speed and reports whether the processing
//! thread keeps up: its CPU use, how far it runs behind, and how long after a
//! note ends the note reaches Dart.
//!
//! cargo run --release --example realtime -- <audio.wav> <piece.json> [--evidence dsp|neural]
//!
//! Audio goes in 512-frame chunks, one per 512/rate seconds of wall time, like
//! a microphone callback. The audio callback itself only downmixes and queues
//! (see the capture_tests in src/audio.rs); the work measured here is the
//! processing thread's.
//!
//! Delivery latency assumes the clip's score time equals its stream time, as
//! in fixtures/real/maestro_heldout (the first note scored where it is played).

mod common;

use native_ffi::audio::start_processing_loop;
use native_ffi::{ACTIVE_PIECE, USER_DATA, USE_NEURAL};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

const CHUNK: usize = 512;

fn thread_cpu() -> Duration {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut ts) };
    Duration::new(ts.tv_sec as u64, ts.tv_nsec as u32)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: realtime <audio.wav> <piece.json> [--evidence dsp|neural]");
        std::process::exit(2);
    }
    USE_NEURAL.store(common::flag(&args, "--evidence") != Some("dsp"), Ordering::Relaxed);
    let (mono, spec) = common::load_wav_mono(&args[1]);
    let rate = spec.sample_rate;
    let piece = common::load_piece(&args[2], 0.0);
    *USER_DATA.lock().unwrap() = None;
    *ACTIVE_PIECE.lock().unwrap() = Some(piece);

    let (tx, rx) = std::sync::mpsc::sync_channel::<Vec<f32>>(2048);
    let worker = std::thread::spawn(move || {
        start_processing_loop(rx, rate);
        thread_cpu()
    });

    // When each record became visible, in ms since the recording started.
    let start = Instant::now();
    let done = Arc::new(AtomicBool::new(false));
    let watcher = {
        let done = done.clone();
        std::thread::spawn(move || {
            let mut seen: Vec<(f32, f32)> = Vec::new(); // (arrived ms, score end ms)
            let mut count = 0;
            while !done.load(Ordering::Relaxed) {
                if let Some(records) = USER_DATA.lock().unwrap().as_ref() {
                    for r in &records[count..] {
                        seen.push((start.elapsed().as_secs_f32() * 1000.0, r.end_time_ms.unwrap_or(0.0)));
                    }
                    count = records.len();
                }
                std::thread::sleep(Duration::from_millis(2));
            }
            seen
        })
    };

    let chunk_s = CHUNK as f64 / rate as f64;
    for (k, chunk) in mono.chunks(CHUNK).enumerate() {
        let due = start + Duration::from_secs_f64(k as f64 * chunk_s);
        if let Some(wait) = due.checked_duration_since(Instant::now()) {
            std::thread::sleep(wait);
        }
        tx.send(chunk.to_vec()).unwrap();
    }
    let audio_s = mono.len() as f64 / rate as f64;
    let fed = Instant::now();
    drop(tx);
    let cpu = worker.join().expect("processing loop panicked");
    let drain = fed.elapsed();
    done.store(true, Ordering::Relaxed);
    let seen = watcher.join().unwrap();

    println!("{}: {rate} Hz, {audio_s:.1} s of audio at live speed", args[1]);
    println!(
        "processing thread CPU: {:.2} s = {:.1}% of one core ({:.2}x real time)",
        cpu.as_secs_f64(),
        100.0 * cpu.as_secs_f64() / audio_s,
        cpu.as_secs_f64() / audio_s
    );
    println!("behind live when the audio ended: {:.0} ms (time to drain and close the last notes)", drain.as_secs_f64() * 1000.0);
    let mut late: Vec<f32> = seen.iter().map(|&(arrived, end)| arrived - end).collect();
    late.sort_by(f32::total_cmp);
    if let (Some(&min), Some(&max)) = (late.first(), late.last()) {
        println!(
            "note delivered after it ended (n={}): min {min:.0} ms, median {:.0} ms, p90 {:.0} ms, max {max:.0} ms",
            late.len(),
            late[late.len() / 2],
            late[(late.len() as f64 * 0.9) as usize]
        );
    }
}
