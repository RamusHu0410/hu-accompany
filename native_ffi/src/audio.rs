use crate::dsp::{Analyzer, Detection, FFT_SIZE, HOP_SIZE};
use crate::models::Notes;
use crate::run_onnx::{neural_evidence, NetFrame, StreamingPitchNet, FRAME_MS};
use crate::tracker::{Frame, NoteTracker, Thresholds};
use crate::templates::NoteTemplates;
use crate::{ACTIVE_PIECE, NOTES_SINK, NOTE_TEMPLATES, USE_NEURAL, USER_DATA};
use std::sync::atomic::Ordering;
use cpal::Stream;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::mpsc::Receiver;
use std::sync::mpsc::Sender;

/// Averages each interleaved frame (L, R, L, R, ...) into one mono sample.
/// Treating interleaved stereo as mono would double the apparent sample rate
/// and halve every detected pitch.
pub fn downmix_to_mono(interleaved: &[f32], channels: usize) -> Vec<f32> {
    if channels <= 1 {
        return interleaved.to_vec();
    }
    interleaved
        .chunks_exact(channels)
        .map(|frame| frame.iter().sum::<f32>() / channels as f32)
        .collect()
}

/// Opens the default mic. Returns the stream plus the device's real sample rate,
/// which the processing loop needs for pitch and timing maths.
/// The stream always delivers mono samples on `tx`.
pub fn create_stream(
    tx: Sender<Vec<f32>>,
) -> Result<(Stream, u32), Box<dyn std::error::Error>> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or("no input device found")?;
    let config = device.default_input_config()?;
    let sample_rate = config.sample_rate().0;
    let channels = config.channels() as usize;
    let err_fn = |err| eprintln!("An error occurred on the audio stream: {}", err);
    let sample_format = config.sample_format();
    let config: cpal::StreamConfig = config.into();
    let stream = match sample_format {
        cpal::SampleFormat::F32 => device.build_input_stream(
            &config,
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                let _ = tx.send(downmix_to_mono(data, channels));
            },
            err_fn,
            None,
        )?,
        other => return Err(format!("unsupported sample format {other:?} (expected f32)").into()),
    };
    stream.play()?;
    Ok((stream, sample_rate))
}

pub fn start_processing_loop(rx: Receiver<Vec<f32>>, sample_rate: u32) {
    if USE_NEURAL.load(Ordering::Relaxed) {
        match StreamingPitchNet::new(sample_rate) {
            Ok(net) => return neural_processing_loop(rx, sample_rate, net),
            Err(e) => eprintln!("pitch network unavailable, using DSP evidence: {e}"),
        }
    }
    let ms_per_sample = 1000.0 / sample_rate as f32;
    let mut analyzer = Analyzer::new(sample_rate);
    let mut tracker: Option<NoteTracker> = None;
    let mut audio_vault: Vec<f32> = Vec::new();
    let mut consumed_samples: u64 = 0; // first sample of the current frame

    // This loop runs when data is received from rx; it ends when the mic stops.
    while let Ok(chunk) = rx.recv() {
        audio_vault.extend_from_slice(&chunk);

        while audio_vault.len() >= FFT_SIZE {
            let frame = Frame {
                start_ms: consumed_samples as f32 * ms_per_sample,
                end_ms: (consumed_samples + FFT_SIZE as u64) as f32 * ms_per_sample,
            };
            if tracker.is_none() {
                tracker = tracker_for_active_piece(Thresholds::DSP);
                if tracker.is_some() {
                    analyzer.set_templates(templates_for_active_piece());
                }
            }
            if let Some(tracker) = tracker.as_mut() {
                // Only run the FFT when some note is expected or still sounding.
                let candidates = tracker.candidates(frame.centre_ms());
                if !candidates.is_empty() {
                    analyzer.analyze(&audio_vault[..FFT_SIZE]);
                    let expected: Vec<f64> = candidates.iter().map(|&i| tracker.pitch_hz(i)).collect();
                    let observations: Vec<(usize, Option<Detection>)> = candidates
                        .iter()
                        .map(|&i| (i, analyzer.evidence(tracker.pitch_hz(i), &expected)))
                        .collect();
                    publish(tracker.update(frame, &observations));
                }
            }
            audio_vault.drain(..HOP_SIZE);
            consumed_samples += HOP_SIZE as u64;
        }
    }

    // Stream closed (recording stopped): notes still sounding end here.
    if let Some(tracker) = tracker.as_mut() {
        let end_ms = (consumed_samples + audio_vault.len() as u64) as f32 * ms_per_sample;
        publish(tracker.finish(end_ms));
    }
}

/// Like the DSP loop, but the tracker steps through the pitch network's frames
/// (86/s), ~100-300 ms behind live (the network's look-ahead plus its run
/// interval; notes are only reported once they end anyway). For each frame the
/// DSP analyser looks at the audio centred on the same moment, for the
/// measured pitch and the re-attack level.
fn neural_processing_loop(rx: Receiver<Vec<f32>>, sample_rate: u32, mut net: StreamingPitchNet) {
    let ms_per_sample = 1000.0 / sample_rate as f32;
    let mut analyzer = Analyzer::new(sample_rate);
    let mut tracker: Option<NoteTracker> = None;
    // Device audio still needed by the DSP analyser; history[0] is sample `history_start`.
    let mut history: Vec<f32> = Vec::new();
    let mut history_start: usize = 0;
    let mut window = vec![0.0f32; FFT_SIZE];

    let mut step = |frames: Vec<NetFrame>, history: &[f32], history_start: usize, tracker: &mut Option<NoteTracker>| {
        for nf in frames {
            if tracker.is_none() {
                *tracker = tracker_for_active_piece(Thresholds::NEURAL);
            }
            let Some(tracker) = tracker.as_mut() else { continue };
            let frame = Frame { start_ms: nf.start_ms(), end_ms: nf.start_ms() + FRAME_MS as f32 };
            let candidates = tracker.candidates(frame.centre_ms());
            if candidates.is_empty() {
                continue;
            }
            // DSP window centred on this frame (zeros before the stream / past the end).
            let centre = (frame.centre_ms() / ms_per_sample) as i64;
            for (j, w) in window.iter_mut().enumerate() {
                let g = centre - (FFT_SIZE / 2) as i64 + j as i64 - history_start as i64;
                *w = if g >= 0 { history.get(g as usize).copied().unwrap_or(0.0) } else { 0.0 };
            }
            analyzer.analyze(&window);
            let expected: Vec<f64> = candidates.iter().map(|&i| tracker.pitch_hz(i)).collect();
            let observations: Vec<(usize, Option<Detection>)> = candidates
                .iter()
                .map(|&i| (i, neural_evidence(&nf, &analyzer, tracker.pitch_hz(i), &expected)))
                .collect();
            publish(tracker.update(frame, &observations));
        }
    };

    while let Ok(chunk) = rx.recv() {
        history.extend_from_slice(&chunk);
        match net.push(&chunk) {
            Ok(frames) => step(frames, &history, history_start, &mut tracker),
            Err(e) => eprintln!("pitch network error: {e}"),
        }
        // The network lags < 1 s; keep 2 s of audio for the DSP windows.
        let keep = 2 * sample_rate as usize;
        if history.len() > keep + sample_rate as usize {
            let drop = history.len() - keep;
            history.drain(..drop);
            history_start += drop;
        }
    }
    if let Ok(frames) = net.finish() {
        step(frames, &history, history_start, &mut tracker);
    }
    if let Some(tracker) = tracker.as_mut() {
        let end_ms = (history_start + history.len()) as f32 * ms_per_sample;
        publish(tracker.finish(end_ms));
    }
}

/// Builds a tracker once a piece is loaded and in a scoring phase.
/// The piece is captured once per recording: stop and restart audio to switch.
fn tracker_for_active_piece(thresholds: Thresholds) -> Option<NoteTracker> {
    let guard = ACTIVE_PIECE.lock().unwrap();
    let piece = guard.as_ref()?;
    // Phases 0 and 1 are scored against the score; 2 and 3 aren't implemented yet.
    matches!(piece.curr_phase, 0 | 1).then(|| NoteTracker::with_thresholds(&piece.notes, thresholds))
}

/// Calibrated note shapes, but only if they were learned on the instrument
/// this piece is for (a piano's harmonics say nothing about a guitar's).
fn templates_for_active_piece() -> Option<NoteTemplates> {
    let instrument = ACTIVE_PIECE.lock().unwrap().as_ref()?.instrument.clone()?;
    let templates = NOTE_TEMPLATES.lock().unwrap().clone()?;
    (templates.instrument == format!("{instrument:?}")).then_some(templates)
}

/// Buffers finished notes and streams them to Dart when it is listening.
/// With no listener (tests, CLI harness) they stay in USER_DATA.
fn publish(notes: Vec<Notes>) {
    if notes.is_empty() {
        return;
    }
    let mut user_data = USER_DATA.lock().unwrap();
    let buffered = user_data.get_or_insert_with(Vec::new);
    buffered.extend(notes);
    if let Some(sink) = NOTES_SINK.read().unwrap().as_ref() {
        let _ = sink.add(std::mem::take(buffered));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dsp::cents;
    use crate::models::{PieceData, TimingSpecs};
    use std::f32::consts::PI;
    use std::sync::Mutex;

    // Tests that drive start_processing_loop share the ACTIVE_PIECE and
    // USER_DATA globals, so they must not run at the same time.
    static LOOP_TEST_LOCK: Mutex<()> = Mutex::new(());

    fn a4_piece(note_id: u64, start_ms: f32, end_ms: f32) -> PieceData {
        PieceData {
            piece_name: "loop test".into(),
            curr_phase: 0,
            instrument: None,
            curr_music_phrase: 0,
            timing: TimingSpecs { bpm: 60.0, beat_unit: 4 },
            notes: vec![Notes {
                note_id,
                pitch_hz: 440.0,
                start_time_ms: Some(start_ms),
                end_time_ms: Some(end_ms),
                duration_ms: Some(end_ms - start_ms),
                is_end: false,
                vibrato_depth: None,
                pedal_action: None,
                has_accent: None,
                markings: None,
            }],
        }
    }

    /// `silence_ms` of silence, `tone_ms` of A4 with harmonics, then `tail_ms`
    /// of silence, sent in mic-sized chunks. Returns this note's records.
    fn run_a4(rate: u32, note_id: u64, silence_ms: f32, tone_ms: f32, tail_ms: f32) -> Vec<Notes> {
        let _serial = LOOP_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        *ACTIVE_PIECE.lock().unwrap() = Some(a4_piece(note_id, silence_ms, silence_ms + tone_ms));
        let samples = |ms: f32| (ms / 1000.0 * rate as f32) as usize;
        let mut audio = vec![0.0f32; samples(silence_ms)];
        audio.extend((0..samples(tone_ms)).map(|i| {
            let t = i as f32 / rate as f32;
            (1..=6).map(|k| 0.3 / k as f32 * (2.0 * PI * 440.0 * k as f32 * t).sin()).sum::<f32>()
        }));
        audio.extend(vec![0.0f32; samples(tail_ms)]);

        let (tx, rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || start_processing_loop(rx, rate));
        for chunk in audio.chunks(512) {
            tx.send(chunk.to_vec()).unwrap();
        }
        drop(tx); // ends the processing loop
        worker.join().unwrap();
        *ACTIVE_PIECE.lock().unwrap() = None;

        let user_data = USER_DATA.lock().unwrap();
        user_data.iter().flatten().filter(|n| n.note_id == note_id).cloned().collect()
    }

    fn assert_close(label: &str, actual: Option<f32>, expected: f32, tolerance: f32) {
        let actual = actual.unwrap_or_else(|| panic!("{label} missing"));
        assert!((actual - expected).abs() <= tolerance, "{label}: expected {expected}±{tolerance}, got {actual}");
    }

    /// Designed timing accuracy. A note is only confirmed once it fills enough
    /// of the ~90 ms window to clearly beat its neighbours, so onsets land
    /// ~25-45 ms late and offsets similarly early (measured on real guitar in
    /// tests/real_audio.rs: median onset bias +31..+48 ms).
    const TIMING_TOLERANCE_MS: f32 = 40.0;

    #[test]
    fn test_note_closes_when_player_goes_silent() {
        let notes = run_a4(44100, 9101, 300.0, 500.0, 500.0);
        assert_eq!(notes.len(), 1, "exactly one record per played note: {notes:?}");
        assert_close("start", notes[0].start_time_ms, 300.0, TIMING_TOLERANCE_MS);
        assert_close("end", notes[0].end_time_ms, 800.0, TIMING_TOLERANCE_MS);
    }

    #[test]
    fn test_48khz_mic_gives_correct_pitch_and_timing() {
        // Real iPhone/Mac mics run at 48 kHz, not 44.1 kHz. A 2 s note makes a
        // wrong-sample-rate bug obvious: timing would be off by ~8.8% = 176 ms,
        // far outside the window-edge tolerance.
        let notes = run_a4(48000, 9201, 300.0, 2000.0, 500.0);
        assert_eq!(notes.len(), 1, "{notes:?}");
        let off = cents(notes[0].pitch_hz, 440.0);
        assert!(off.abs() < 10.0, "pitch {} Hz is {off:+.1} cents off", notes[0].pitch_hz);
        assert_close("start", notes[0].start_time_ms, 300.0, TIMING_TOLERANCE_MS);
        assert_close("end", notes[0].end_time_ms, 2300.0, TIMING_TOLERANCE_MS);
    }

    #[test]
    fn test_note_still_sounding_when_recording_stops_is_closed() {
        let notes = run_a4(44100, 9301, 300.0, 700.0, 0.0);
        assert_eq!(notes.len(), 1, "note cut off by stop must still be reported: {notes:?}");
        assert_close("end", notes[0].end_time_ms, 1000.0, TIMING_TOLERANCE_MS);
    }
}

#[cfg(test)]
mod downmix_tests {
    use super::downmix_to_mono;

    #[test]
    fn test_stereo_frames_are_averaged() {
        assert_eq!(downmix_to_mono(&[1.0, 3.0, 2.0, 4.0], 2), vec![2.0, 3.0]);
    }

    #[test]
    fn test_mono_passes_through() {
        assert_eq!(downmix_to_mono(&[0.1, 0.2, 0.3], 1), vec![0.1, 0.2, 0.3]);
    }

    #[test]
    fn test_partial_trailing_frame_is_dropped() {
        // cpal always delivers whole frames; guard against a torn one anyway.
        assert_eq!(downmix_to_mono(&[1.0, 1.0, 5.0], 2), vec![1.0]);
    }
}
