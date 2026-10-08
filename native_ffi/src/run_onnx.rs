//! Neural pitch evidence from Spotify's Basic Pitch model (Apache-2.0, bundled
//! in assets/, see assets/NOTICE), run with tract (pure Rust, no native libs).
//!
//! The network outputs, 86 times a second, how likely each of the 88 piano
//! keys is sounding. Trained on real recordings of many instruments, it tells
//! thick chords apart where hand-built spectral rules run out (octave
//! doublings, consonant neighbours). The score still decides WHICH keys we ask
//! about; see dsp.rs and tracker.rs for how its answer is used.

use crate::dsp::{cents, Analyzer, Detection};
use rubato::audioadapter_buffers::direct::InterleavedSlice;
use rubato::{Fft, FixedSync, Indexing, Resampler};
use tract_onnx::prelude::*;

/// Sample rate the model was trained on.
pub const MODEL_RATE: u32 = 22050;
/// Samples per output frame (86.1 frames/s, 11.6 ms each).
pub const FRAME_HOP: usize = 256;
/// Samples per model input window (~2 s).
pub const WINDOW: usize = 43844;
/// Output frames per window.
pub const WINDOW_FRAMES: usize = 172;
pub const KEYS: usize = 88;
/// MIDI number of the model's first key (A0).
pub const LOWEST_MIDI: i32 = 21;
/// A frame is only released once the model has heard this many frames after
/// it (~105 ms). The network looks both ways in time; with less future audio
/// its last frames are unsure. Measured on the piano sets: 0 ms already works,
/// ~100 ms matches offline accuracy.
pub const LOOKAHEAD_FRAMES: i64 = 9;
/// Re-run the network every this many new frames (~186 ms). Each run costs
/// ~50 ms on a laptop core for 2 s of audio, so this sets the CPU load.
pub const RUN_EVERY_FRAMES: usize = 16;
/// Frame duration in milliseconds.
pub const FRAME_MS: f64 = FRAME_HOP as f64 * 1000.0 / MODEL_RATE as f64;

static MODEL: &[u8] = include_bytes!("../assets/basic_pitch_nmp.onnx");
/// The model's per-key "note is sounding" output (the others are onsets and
/// a finer pitch contour).
const NOTE_OUTPUT: &str = "StatefulPartitionedCall:1";

/// One output frame: how likely each key is sounding, 0..=1.
#[derive(Clone, Debug)]
pub struct NetFrame {
    /// Global frame number since the stream started (frame start = index × FRAME_MS).
    pub index: i64,
    pub keys: [f32; KEYS],
}

impl NetFrame {
    pub fn start_ms(&self) -> f32 {
        (self.index as f64 * FRAME_MS) as f32
    }
    /// Activation of the key nearest `hz` (0 outside the piano range).
    pub fn key_activation(&self, hz: f64) -> f32 {
        key_index(hz).map_or(0.0, |k| self.keys[k])
    }
}

/// Index of the key nearest `hz` in the model's output, if on the piano.
pub fn key_index(hz: f64) -> Option<usize> {
    let midi = (69.0 + 12.0 * (hz / 440.0).log2()).round() as i32;
    let k = midi - LOWEST_MIDI;
    (0..KEYS as i32).contains(&k).then_some(k as usize)
}

/// Evidence that `target_hz` sounds in network frame `frame`: its key's
/// activation (confidence) and that activation over the strongest semitone
/// neighbour the score doesn't expect (dominance: a wrong note mostly shows up
/// as spill-over from the real note next door, which the network rates higher).
/// Pitch in cents and the attack level come from `analyzer`, which must have
/// analysed audio centred on the same moment.
pub fn neural_evidence(frame: &NetFrame, analyzer: &Analyzer, target_hz: f64, expected_hz: &[f64]) -> Option<Detection> {
    let confidence = frame.keys[key_index(target_hz)?];
    let strongest_rival = [-1.0, 1.0]
        .into_iter()
        .map(|semitones| target_hz * 2f64.powf(semitones / 12.0))
        .filter(|&n| !expected_hz.iter().any(|&e| cents(e, n).abs() < 50.0))
        .map(|n| frame.key_activation(n))
        .fold(0.0, f32::max);
    let dominance = if strongest_rival > 0.0 { confidence / strongest_rival } else { f32::INFINITY };
    let pitch_hz = analyzer.measured_pitch(target_hz).filter(|&p| cents(p, target_hz).abs() < 50.0).unwrap_or(target_hz);
    Some(Detection { pitch_hz, dominance, attack_level: analyzer.attack_level(target_hz), share: 1.0, confidence })
}

pub struct PitchNet {
    plan: Arc<TypedRunnableModel>,
}

impl PitchNet {
    pub fn new() -> TractResult<Self> {
        let mut model = tract_onnx::onnx()
            .model_for_read(&mut std::io::Cursor::new(MODEL))?
            .with_input_fact(0, f32::fact([1, WINDOW, 1]).into())?;
        let note = model
            .find_outlet_label(NOTE_OUTPUT)
            .ok_or_else(|| TractError::msg(format!("model has no output {NOTE_OUTPUT}")))?;
        model.select_output_outlets(&[note])?;
        let plan = model.into_optimized()?.into_runnable()?;
        Ok(Self { plan })
    }

    /// Key activations for one window of WINDOW samples at MODEL_RATE:
    /// frame i covers samples i·FRAME_HOP onwards.
    pub fn infer(&self, window: &[f32]) -> TractResult<Vec<[f32; KEYS]>> {
        assert_eq!(window.len(), WINDOW, "window must be WINDOW samples");
        let input: Tensor = tract_ndarray::Array3::from_shape_vec((1, WINDOW, 1), window.to_vec())?.into();
        let out = self.plan.run(tvec!(input.into()))?;
        let view = out[0].to_plain_array_view::<f32>()?;
        Ok((0..view.shape()[1])
            .map(|f| std::array::from_fn(|k| view[[0, f, k]]))
            .collect())
    }
}

/// Runs the network over a live stream: device-rate samples in, each output
/// frame out exactly once, in order, LOOKAHEAD_FRAMES after it was heard.
pub struct StreamingPitchNet {
    net: PitchNet,
    resampler: Option<Fft<f32>>,
    /// Device samples waiting for a full resampler chunk.
    pending: Vec<f32>,
    /// Resampler output still to drop: its fixed delay, so that model sample
    /// n is device time n / MODEL_RATE.
    delay_left: usize,
    /// Model-rate audio; audio[0] is global sample `audio_start`.
    audio: Vec<f32>,
    audio_start: usize,
    /// Model-rate samples received (the real ones; see `finish`).
    received: usize,
    device_rate: u32,
    /// Device samples received in total.
    device_received: usize,
    /// End (exclusive, global sample) of the last window the network ran on.
    last_run_end: i64,
    next_frame: i64,
}

impl StreamingPitchNet {
    pub fn new(device_rate: u32) -> TractResult<Self> {
        let resampler = (device_rate != MODEL_RATE)
            .then(|| Fft::<f32>::new(device_rate as usize, MODEL_RATE as usize, 1024, 1, 1, FixedSync::Input))
            .transpose()
            .map_err(|e| TractError::msg(format!("resampler: {e}")))?;
        let delay_left = resampler.as_ref().map_or(0, |r| r.output_delay());
        Ok(Self {
            net: PitchNet::new()?,
            resampler,
            pending: Vec::new(),
            delay_left,
            audio: Vec::new(),
            audio_start: 0,
            received: 0,
            device_rate,
            device_received: 0,
            last_run_end: i64::MIN,
            next_frame: 0,
        })
    }

    /// Feeds mono samples at the device rate; returns the frames that became final.
    pub fn push(&mut self, device_samples: &[f32]) -> TractResult<Vec<NetFrame>> {
        self.pending.extend_from_slice(device_samples);
        self.device_received += device_samples.len();
        self.resample(false)?;
        self.run(false)
    }

    /// End of stream: returns every remaining frame of the audio received.
    pub fn finish(&mut self) -> TractResult<Vec<NetFrame>> {
        self.resample(true)?;
        // The resampler's delay holds back the last real samples until the
        // flush, so count real audio from the device side instead.
        let real = (self.device_received as u64 * MODEL_RATE as u64).div_ceil(self.device_rate as u64) as usize;
        self.received = real.min(self.audio_start + self.audio.len());
        self.run(true)
    }

    fn resample(&mut self, flush: bool) -> TractResult<()> {
        let Some(r) = self.resampler.as_mut() else {
            let samples = std::mem::take(&mut self.pending);
            self.append(&samples, true);
            return Ok(());
        };
        if flush {
            // Push silence through so the delayed tail of the real audio comes out.
            let pad = r.input_frames_next() * 2 + r.output_delay() * 2;
            self.pending.extend(std::iter::repeat_n(0.0, pad));
        }
        let mut out = vec![0.0f32; r.output_frames_max()];
        let mut produced = Vec::new();
        while self.pending.len() >= r.input_frames_next() {
            let n_in = r.input_frames_next();
            let input = InterleavedSlice::new(&self.pending[..n_in], 1, n_in).map_err(|e| TractError::msg(e.to_string()))?;
            let cap = out.len();
            let mut output = InterleavedSlice::new_mut(&mut out, 1, cap).map_err(|e| TractError::msg(e.to_string()))?;
            let indexing = Indexing { input_offset: 0, output_offset: 0, active_channels_mask: None, partial_len: None };
            let (read, written) =
                r.process_into_buffer(&input, &mut output, Some(&indexing)).map_err(|e| TractError::msg(e.to_string()))?;
            self.pending.drain(..read);
            let skip = self.delay_left.min(written);
            self.delay_left -= skip;
            produced.extend_from_slice(&out[skip..written]);
        }
        if flush {
            self.pending.clear();
        }
        // Samples produced only by the flush padding aren't real audio.
        self.append(&produced, !flush);
        Ok(())
    }

    fn append(&mut self, samples: &[f32], real: bool) {
        self.audio.extend_from_slice(samples);
        if real {
            self.received = self.audio_start + self.audio.len();
        }
    }

    /// Window ends sit on a grid (end = WINDOW + n·FRAME_HOP), so a window's
    /// output frame i is always global frame n + i.
    fn align_up(sample: i64) -> i64 {
        let offset = WINDOW as i64 % FRAME_HOP as i64;
        sample + (offset - sample).rem_euclid(FRAME_HOP as i64)
    }

    /// Runs every window that is due, in order: one per RUN_EVERY_FRAMES
    /// frames of new audio, so no frame is skipped however big a push is.
    /// When flushing, steps on (over silence) until the last real frame has
    /// had its LOOKAHEAD_FRAMES.
    fn run(&mut self, flush: bool) -> TractResult<Vec<NetFrame>> {
        let hop = FRAME_HOP as i64;
        let step = (RUN_EVERY_FRAMES * FRAME_HOP) as i64;
        let available = (self.audio_start + self.audio.len()) as i64;
        let last_real = (self.received as i64 - 1).div_euclid(hop);
        // Smallest window end that gives the last real frame its look-ahead.
        let final_end = Self::align_up((last_real + 1 + LOOKAHEAD_FRAMES) * hop);
        if self.last_run_end == i64::MIN {
            // First window: as soon as the first frames can have their look-ahead.
            self.last_run_end = Self::align_up((RUN_EVERY_FRAMES as i64 + 1 + LOOKAHEAD_FRAMES) * hop) - step;
        }
        let mut released = Vec::new();
        loop {
            let mut end = self.last_run_end + step;
            if flush {
                if self.next_frame > last_real || self.received == 0 {
                    break;
                }
                end = end.min(final_end).max(self.last_run_end + hop);
            } else if end > available {
                break;
            }
            let start = end - WINDOW as i64;
            let window: Vec<f32> = (start..end)
                .map(|g| {
                    let i = g - self.audio_start as i64;
                    if g < 0 || g >= self.received as i64 || i < 0 { 0.0 } else { self.audio.get(i as usize).copied().unwrap_or(0.0) }
                })
                .collect();
            let frames = self.net.infer(&window)?;
            let first = start / hop;
            for (i, keys) in frames.into_iter().enumerate() {
                let index = first + i as i64;
                let heard_after = end.div_euclid(hop) - (index + 1); // whole frames heard past this one
                if index < self.next_frame || index < 0 || index > last_real || heard_after < LOOKAHEAD_FRAMES {
                    continue;
                }
                released.push(NetFrame { index, keys });
                self.next_frame = index + 1;
            }
            self.last_run_end = end;
            // Keep only what the next window can still need.
            let keep_from = (end + step - WINDOW as i64).max(0) as usize;
            if keep_from > self.audio_start {
                let drop = (keep_from - self.audio_start).min(self.audio.len());
                self.audio.drain(..drop);
                self.audio_start += drop;
            }
        }
        Ok(released)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    /// `secs` of audio at `rate`: A4 with harmonics between `on` and `off` s.
    fn a4_burst(rate: u32, secs: f32, on: f32, off: f32) -> Vec<f32> {
        (0..(secs * rate as f32) as usize)
            .map(|i| {
                let t = i as f32 / rate as f32;
                if t < on || t >= off {
                    return 0.0;
                }
                (1..=6).map(|k| 0.3 / k as f32 * (2.0 * PI * 440.0 * k as f32 * t).sin()).sum()
            })
            .collect()
    }

    const A4: usize = 69 - LOWEST_MIDI as usize;

    #[test]
    fn test_neural_evidence_compares_with_unexpected_neighbours_only() {
        let mut keys = [0.0f32; KEYS];
        keys[A4] = 0.8;
        keys[A4 - 1] = 0.4; // G#4
        keys[A4 + 1] = 0.1; // A#4
        let frame = NetFrame { index: 0, keys };
        let mut analyzer = Analyzer::new(44100);
        analyzer.analyze(&a4_burst(44100, crate::dsp::FFT_SIZE as f32 / 44100.0, 0.0, 1.0));
        let (g_sharp4, a4) = (415.30, 440.0);
        let d = neural_evidence(&frame, &analyzer, a4, &[a4]).unwrap();
        assert_eq!(d.confidence, 0.8);
        assert!((d.dominance - 2.0).abs() < 1e-5, "vs G#4: {}", d.dominance);
        assert!((d.pitch_hz - a4).abs() < 1.0, "measured {}", d.pitch_hz);
        // G#4 expected too (cluster chord): only A#4 is a rival.
        let d = neural_evidence(&frame, &analyzer, a4, &[a4, g_sharp4]).unwrap();
        assert!((d.dominance - 8.0).abs() < 1e-4, "vs A#4: {}", d.dominance);
    }

    #[test]
    fn test_network_hears_a4_and_not_its_neighbours() {
        let net = PitchNet::new().unwrap();
        let frames = net.infer(&a4_burst(MODEL_RATE, WINDOW as f32 / MODEL_RATE as f32, 0.0, 1.0)).unwrap();
        assert_eq!(frames.len(), WINDOW_FRAMES);
        let mid = &frames[40]; // ~0.46 s, inside the tone
        assert!(mid[A4] > 0.5, "A4 activation {}", mid[A4]);
        assert!(mid[A4 - 1] < 0.2 && mid[A4 + 1] < 0.2, "neighbours {} {}", mid[A4 - 1], mid[A4 + 1]);
        assert!(frames[150][A4] < 0.2, "silence at 1.7 s reads {}", frames[150][A4]);
    }

    /// Streams `audio` in uneven chunks; returns every released frame.
    fn stream(rate: u32, audio: &[f32]) -> Vec<NetFrame> {
        let mut net = StreamingPitchNet::new(rate).unwrap();
        let mut out = Vec::new();
        let mut pos = 0;
        for (n, size) in [512usize, 480, 1024, 333].iter().cycle().enumerate() {
            if pos >= audio.len() {
                break;
            }
            let end = (pos + size).min(audio.len());
            out.extend(net.push(&audio[pos..end]).unwrap());
            pos = end;
            let _ = n;
        }
        out.extend(net.finish().unwrap());
        out
    }

    #[test]
    fn test_stream_releases_every_frame_once_and_in_order() {
        let frames = stream(44100, &a4_burst(44100, 3.0, 1.0, 2.0));
        let indices: Vec<i64> = frames.iter().map(|f| f.index).collect();
        let expected_count = (3.0 * MODEL_RATE as f64 / FRAME_HOP as f64).ceil() as i64;
        assert_eq!(indices.first(), Some(&0));
        assert!(indices.windows(2).all(|w| w[1] == w[0] + 1), "gap or repeat in frame indices");
        assert!((indices.len() as i64 - expected_count).abs() <= 1, "{} frames for 3 s, expected ~{expected_count}", indices.len());
    }

    #[test]
    fn test_one_huge_push_skips_no_frames() {
        let audio = a4_burst(44100, 5.0, 1.0, 2.0);
        let mut net = StreamingPitchNet::new(44100).unwrap();
        let mut frames = net.push(&audio).unwrap();
        frames.extend(net.finish().unwrap());
        let indices: Vec<i64> = frames.iter().map(|f| f.index).collect();
        assert_eq!(indices.first(), Some(&0));
        assert!(indices.windows(2).all(|w| w[1] == w[0] + 1), "gap or repeat in frame indices");
        let expected = (5.0 * MODEL_RATE as f64 / FRAME_HOP as f64).ceil() as i64;
        assert!((indices.len() as i64 - expected).abs() <= 1, "{} frames for 5 s, expected ~{expected}", indices.len());
    }

    #[test]
    fn test_stream_frames_line_up_with_the_audio_at_44k_and_48k() {
        for rate in [44100, 48000] {
            let frames = stream(rate, &a4_burst(rate, 3.0, 1.0, 2.0));
            let mean = |from_ms: f32, to_ms: f32| {
                let sel: Vec<f32> = frames.iter().filter(|f| (from_ms..to_ms).contains(&f.start_ms())).map(|f| f.keys[A4]).collect();
                sel.iter().sum::<f32>() / sel.len().max(1) as f32
            };
            assert!(mean(1150.0, 1850.0) > 0.5, "{rate} Hz: tone reads {}", mean(1150.0, 1850.0));
            assert!(mean(300.0, 850.0) < 0.2, "{rate} Hz: silence before reads {}", mean(300.0, 850.0));
            assert!(mean(2200.0, 2800.0) < 0.2, "{rate} Hz: silence after reads {}", mean(2200.0, 2800.0));
            // The onset edge: first frame above 0.5 within ~2 frames of 1.0 s.
            let first = frames.iter().find(|f| f.keys[A4] > 0.5).map(|f| f.start_ms()).unwrap();
            assert!((first - 1000.0).abs() <= 2.5 * FRAME_MS as f32, "{rate} Hz: tone starts at {first} ms, audio at 1000 ms");
        }
    }

    #[test]
    fn test_frames_are_released_within_lookahead_plus_run_interval() {
        let rate = 44100;
        let audio = a4_burst(rate, 3.0, 1.0, 2.0);
        let mut net = StreamingPitchNet::new(rate).unwrap();
        let mut worst_lag_frames = 0i64;
        for chunk in audio.chunks(512) {
            let heard_frames = (net.received as f64 / FRAME_HOP as f64) as i64;
            let _ = heard_frames;
            for f in net.push(chunk).unwrap() {
                let heard = (net.received / FRAME_HOP) as i64;
                worst_lag_frames = worst_lag_frames.max(heard - f.index);
            }
        }
        let limit = LOOKAHEAD_FRAMES + RUN_EVERY_FRAMES as i64 + 6; // + resampler delay, chunking
        assert!(worst_lag_frames <= limit, "frames released up to {worst_lag_frames} frames late (limit {limit})");
    }
}
