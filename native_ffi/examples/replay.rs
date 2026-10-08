//! Replays a WAV recording through the real detection pipeline, no Flutter needed.
//!
//! cargo run --example replay -- <audio.wav> <piece.json> [--offset-ms N]
//!
//! Any WAV works: 16/24/32-bit int or 32-bit float, mono or multi-channel, any
//! sample rate. Samples go through the same downmix + start_processing_loop as
//! the live mic, in mic-sized chunks.

mod common;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: replay <audio.wav> <piece.json> [--offset-ms N]");
        std::process::exit(2);
    }
    let offset_ms: f32 = common::flag(&args, "--offset-ms")
        .map(|v| v.parse().expect("--offset-ms must be a number"))
        .unwrap_or(0.0);

    let (mono, spec) = common::load_wav_mono(&args[1]);
    println!(
        "{}: {} Hz, {} ch, {}-bit {:?}, {:.2} s",
        args[1],
        spec.sample_rate,
        spec.channels,
        spec.bits_per_sample,
        spec.sample_format,
        mono.len() as f32 / spec.sample_rate as f32
    );

    let piece = common::load_piece(&args[2], offset_ms);
    let records = common::run_pipeline(&mono, spec.sample_rate, &piece);
    common::print_report(&piece, &records);
}
