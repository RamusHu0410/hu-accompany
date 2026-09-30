//! Score-informed note detection: "is this expected note sounding right now?"
//!
//! We never transcribe blindly. The score tells us which notes should be
//! sounding, so for each one we only ask whether its harmonic series stands out
//! (a) above the room's noise floor and (b) above the same series one semitone
//! higher and lower. That works for single notes and chords alike.

use num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::sync::Arc;

/// Analysis window: 4096 samples ≈ 93 ms at 44.1 kHz / 85 ms at 48 kHz.
/// Longer windows resolve low notes better but react later.
pub const FFT_SIZE: usize = 4096;
/// Step between analyses: 256 samples ≈ 5.8 ms at 44.1 kHz.
pub const HOP_SIZE: usize = 256;

/// Harmonics summed per note. Higher harmonics are further apart in Hz, which
/// is what separates neighbouring semitones for low notes.
const MAX_HARMONICS: usize = 8;
/// Harmonics above this are weak and noisy on real instruments.
const MAX_HARMONIC_HZ: f64 = 5000.0;
/// Lowest frequency considered for the noise floor.
const MIN_BAND_HZ: f64 = 50.0;
/// Search this far around each expected harmonic (tuning, vibrato, stretch).
const SEARCH_CENTS: f64 = 30.0;
/// A Hann window's main lobe spans ±2 bins; neighbours this far apart don't
/// leak into each other's peaks.
const MIN_SEMITONE_GAP_BINS: f64 = 3.0;
/// A note must beat each non-expected semitone neighbour by this factor.
pub const NEIGHBOUR_RATIO: f32 = 1.5;
/// A note's loudest harmonic must be this far above the spectral median.
pub const FLOOR_RATIO: f32 = 10.0;
/// Anything quieter than this is treated as silence.
const MIN_LEVEL_DBFS: f32 = -75.0;
/// Newest samples used to time re-attacks (2048 ≈ 46 ms at 44.1 kHz). The
/// long window mixes ~90 ms of old ring into every frame, so a quiet re-strum
/// of a ringing string barely moves it; a short window sees the fresh strike.
/// Too short and beating between strings looks like attacks (see tracker.rs).
pub const ATTACK_WINDOW: usize = 2048;

/// How strongly one expected note is present in one frame.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Detection {
    /// Measured pitch (what the player actually played).
    pub pitch_hz: f64,
    /// Harmonic salience of the note ÷ that of its strongest rival semitone
    /// neighbour. 1.0 = can't tell them apart; infinity = no rival at all.
    pub dominance: f32,
    /// How strongly the note's harmonics sound in the newest ATTACK_WINDOW
    /// samples. Absolute scale is arbitrary; only ratios over time mean
    /// something (a re-pluck of a ringing string shows up as a jump, see tracker.rs).
    pub attack_level: f32,
}

/// Distance between two pitches in cents (100 cents = 1 semitone).
pub fn cents(hz: f64, reference_hz: f64) -> f64 {
    1200.0 * (hz / reference_hz).log2()
}

pub struct Analyzer {
    bin_hz: f64,
    fft: Arc<dyn RealToComplex<f32>>,
    window: Vec<f32>,
    input: Vec<f32>,
    spectrum: Vec<Complex<f32>>,
    scratch: Vec<Complex<f32>>,
    mags: Vec<f32>,
    floor_scratch: Vec<f32>,
    noise_floor: f32,
    min_peak: f32,
    short: ShortSpectrum,
}

/// Magnitude spectrum of the newest ATTACK_WINDOW samples of each frame.
struct ShortSpectrum {
    bin_hz: f64,
    fft: Arc<dyn RealToComplex<f32>>,
    window: Vec<f32>,
    input: Vec<f32>,
    spectrum: Vec<Complex<f32>>,
    scratch: Vec<Complex<f32>>,
    mags: Vec<f32>,
}

impl ShortSpectrum {
    fn new(sample_rate: u32) -> Self {
        let fft = RealFftPlanner::<f32>::new().plan_fft_forward(ATTACK_WINDOW);
        Self {
            bin_hz: sample_rate as f64 / ATTACK_WINDOW as f64,
            window: hann(ATTACK_WINDOW),
            input: fft.make_input_vec(),
            spectrum: fft.make_output_vec(),
            scratch: fft.make_scratch_vec(),
            mags: vec![0.0; ATTACK_WINDOW / 2 + 1],
            fft,
        }
    }

    fn analyze(&mut self, newest: &[f32]) {
        for ((dst, &s), &w) in self.input.iter_mut().zip(newest).zip(&self.window) {
            *dst = s * w;
        }
        self.fft
            .process_with_scratch(&mut self.input, &mut self.spectrum, &mut self.scratch)
            .expect("buffer sizes are fixed at construction");
        for (m, c) in self.mags.iter_mut().zip(&self.spectrum) {
            *m = c.norm();
        }
    }

    /// Sum of the peaks (±1 bin) at the first MAX_HARMONICS harmonics of `hz`.
    /// Bins here are too wide to separate semitones; that is fine, the long
    /// window has already decided *which* note this is, this only says *when*.
    fn level(&self, hz: f64) -> f32 {
        (1..=MAX_HARMONICS)
            .map(|k| k as f64 * hz)
            .take_while(|&f| f <= MAX_HARMONIC_HZ)
            .map(|f| {
                let centre = (f / self.bin_hz).round() as usize;
                let lo = centre.saturating_sub(1).max(1);
                let hi = (centre + 1).min(self.mags.len() - 1);
                self.mags[lo..=hi].iter().copied().fold(0.0, f32::max)
            })
            .sum()
    }
}

/// Hann window: tapers the frame edges so a note's energy stays in a few bins
/// instead of smearing across the spectrum.
fn hann(n: usize) -> Vec<f32> {
    (0..n)
        .map(|i| {
            let x = std::f32::consts::PI * i as f32 / n as f32;
            x.sin().powi(2)
        })
        .collect()
}

impl Analyzer {
    pub fn new(sample_rate: u32) -> Self {
        let fft = RealFftPlanner::<f32>::new().plan_fft_forward(FFT_SIZE);
        let window = hann(FFT_SIZE);
        // A full-scale sine through a Hann window peaks at FFT_SIZE / 4.
        let min_peak = 10f32.powf(MIN_LEVEL_DBFS / 20.0) * FFT_SIZE as f32 / 4.0;
        Self {
            bin_hz: sample_rate as f64 / FFT_SIZE as f64,
            input: fft.make_input_vec(),
            spectrum: fft.make_output_vec(),
            scratch: fft.make_scratch_vec(),
            mags: vec![0.0; FFT_SIZE / 2 + 1],
            floor_scratch: Vec::with_capacity(FFT_SIZE / 2),
            noise_floor: 0.0,
            short: ShortSpectrum::new(sample_rate),
            fft,
            window,
            min_peak,
        }
    }

    /// Analyses one frame of exactly FFT_SIZE mono samples.
    pub fn analyze(&mut self, frame: &[f32]) {
        assert_eq!(frame.len(), FFT_SIZE, "frame must be FFT_SIZE samples");
        for ((dst, &s), &w) in self.input.iter_mut().zip(frame).zip(&self.window) {
            *dst = s * w;
        }
        self.fft
            .process_with_scratch(&mut self.input, &mut self.spectrum, &mut self.scratch)
            .expect("buffer sizes are fixed at construction");
        for (m, c) in self.mags.iter_mut().zip(&self.spectrum) {
            *m = c.norm();
        }
        self.short.analyze(&frame[FFT_SIZE - ATTACK_WINDOW..]);

        // Noise floor = median magnitude across the musical band. Notes only
        // occupy a few bins, so the median tracks the room (hiss, hum, chatter)
        // rather than the music, and adapts every frame.
        let lo = (MIN_BAND_HZ / self.bin_hz).ceil() as usize;
        let hi = ((MAX_HARMONIC_HZ / self.bin_hz) as usize).min(self.mags.len() - 1);
        self.floor_scratch.clear();
        self.floor_scratch.extend_from_slice(&self.mags[lo..=hi]);
        let mid = self.floor_scratch.len() / 2;
        let (_, median, _) = self.floor_scratch.select_nth_unstable_by(mid, f32::total_cmp);
        self.noise_floor = *median;
    }

    /// Largest bin within ±SEARCH_CENTS (at least ±1 bin) of `hz`.
    fn peak_near(&self, hz: f64) -> Option<(usize, f32)> {
        let centre = hz / self.bin_hz;
        let radius = (centre * (2f64.powf(SEARCH_CENTS / 1200.0) - 1.0)).max(1.0);
        let lo = ((centre - radius).round() as usize).max(1);
        let hi = ((centre + radius).round() as usize).min(self.mags.len() - 2);
        (lo..=hi)
            .map(|b| (b, self.mags[b]))
            .max_by(|a, b| a.1.total_cmp(&b.1))
    }

    /// First harmonic of `hz` whose semitone neighbours sit at least
    /// MIN_SEMITONE_GAP_BINS away. Below it, a note and its neighbour share the
    /// same FFT peak and can't be told apart, so low notes are judged on their
    /// upper harmonics (E2 from the 7th, C4 from the 3rd, at 44.1 kHz).
    fn first_resolvable_harmonic(&self, hz: f64) -> usize {
        let gap_hz_per_harmonic = hz * (2f64.powf(1.0 / 12.0) - 1.0);
        ((MIN_SEMITONE_GAP_BINS * self.bin_hz / gap_hz_per_harmonic).ceil() as usize).max(1)
    }

    /// Resolvable harmonic peaks of a note judged at `note_hz`, evaluated at
    /// `hz` (the note itself or a semitone neighbour, so both use the same
    /// harmonic numbers): (harmonic number, bin, magnitude).
    fn harmonic_peaks(&self, note_hz: f64, hz: f64) -> impl Iterator<Item = (usize, usize, f32)> + '_ {
        let nyquist = self.bin_hz * (self.mags.len() - 2) as f64;
        let first = self.first_resolvable_harmonic(note_hz);
        (first..first + MAX_HARMONICS)
            .take_while(move |&k| k as f64 * hz <= MAX_HARMONIC_HZ.min(nyquist))
            .filter_map(move |k| self.peak_near(k as f64 * hz).map(|(b, m)| (k, b, m)))
    }

    /// Sum of harmonic peaks: how strongly the harmonic series of `hz` is present.
    fn salience(&self, note_hz: f64, hz: f64) -> f32 {
        self.harmonic_peaks(note_hz, hz).map(|(_, _, m)| m).sum()
    }

    /// Evidence that `target_hz` is sounding in the last analysed frame, or
    /// None if it isn't above the noise floor at all.
    ///
    /// `expected_hz` = every note the score expects right now (chord mates).
    /// A semitone neighbour that is itself expected is not treated as a rival:
    /// in a cluster chord both are supposed to sound.
    ///
    /// The caller decides how much dominance is enough (see tracker.rs: it
    /// takes more to start a note than to keep one going).
    pub fn evidence(&self, target_hz: f64, expected_hz: &[f64]) -> Option<Detection> {
        let loudest = self
            .harmonic_peaks(target_hz, target_hz)
            .map(|(_, _, m)| m)
            .fold(0.0, f32::max);
        if loudest < self.min_peak || loudest < FLOOR_RATIO * self.noise_floor {
            return None;
        }
        let salience = self.salience(target_hz, target_hz);
        let strongest_rival = [-1.0, 1.0]
            .into_iter()
            .map(|semitones| target_hz * 2f64.powf(semitones / 12.0))
            .filter(|&n| !expected_hz.iter().any(|&e| cents(e, n).abs() < 50.0))
            .map(|n| self.salience(target_hz, n))
            .fold(0.0, f32::max);
        let dominance = if strongest_rival > 0.0 { salience / strongest_rival } else { f32::INFINITY };
        Some(Detection {
            pitch_hz: self.estimate_pitch(target_hz)?,
            dominance,
            attack_level: self.short.level(target_hz),
        })
    }

    /// Single-frame yes/no at NEIGHBOUR_RATIO: the measured pitch if
    /// `target_hz` is sounding. The live pipeline uses `evidence` instead.
    pub fn detect(&self, target_hz: f64, expected_hz: &[f64]) -> Option<f64> {
        self.evidence(target_hz, expected_hz)
            .filter(|d| d.dominance >= NEIGHBOUR_RATIO)
            .map(|d| d.pitch_hz)
    }

    /// Refines the pitch from the strongest of the first 4 resolvable
    /// harmonics, using parabolic interpolation on log magnitudes (accurate to
    /// a few cents with a Hann window), then divides by the harmonic number.
    /// Higher harmonics sit at higher bins, so the same bin error costs fewer cents.
    fn estimate_pitch(&self, target_hz: f64) -> Option<f64> {
        let (k, bin, _) = self
            .harmonic_peaks(target_hz, target_hz)
            .take(4)
            .max_by(|a, b| a.2.total_cmp(&b.2))?;
        let ln = |b: usize| (self.mags[b].max(1e-12) as f64).ln();
        let (a, b, c) = (ln(bin - 1), ln(bin), ln(bin + 1));
        let denom = a - 2.0 * b + c;
        let offset = if denom.abs() > 1e-12 { (0.5 * (a - c) / denom).clamp(-0.5, 0.5) } else { 0.0 };
        Some((bin as f64 + offset) * self.bin_hz / k as f64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    const SR: u32 = 44100;
    const C4: f64 = 261.63;
    const E4: f64 = 329.63;
    const G4: f64 = 392.00;

    fn semitones(hz: f64, n: f64) -> f64 {
        hz * 2f64.powf(n / 12.0)
    }

    /// Plucked-string-like tone: harmonic k has amplitude 1/k.
    fn instrument_tone(f0: f64, amplitude: f32) -> Vec<f32> {
        (0..FFT_SIZE)
            .map(|i| {
                let t = i as f32 / SR as f32;
                (1..=10)
                    .map(|k| amplitude / k as f32 * (2.0 * PI * k as f32 * f0 as f32 * t).sin())
                    .sum()
            })
            .collect()
    }

    fn mix(parts: &[Vec<f32>]) -> Vec<f32> {
        (0..FFT_SIZE).map(|i| parts.iter().map(|p| p[i]).sum()).collect()
    }

    fn analyzed(frame: &[f32]) -> Analyzer {
        let mut a = Analyzer::new(SR);
        a.analyze(frame);
        a
    }

    #[test]
    fn test_c4_detected_with_accurate_pitch() {
        let a = analyzed(&instrument_tone(C4, 0.2));
        let hz = a.detect(C4, &[C4]).expect("C4 should be detected");
        assert!(cents(hz, C4).abs() < 5.0, "measured {hz} Hz ({:+.1} cents)", cents(hz, C4));
    }

    #[test]
    fn test_semitone_neighbours_of_played_note_are_rejected() {
        let a = analyzed(&instrument_tone(C4, 0.2));
        assert_eq!(a.detect(semitones(C4, -1.0), &[semitones(C4, -1.0)]), None, "B3");
        assert_eq!(a.detect(semitones(C4, 1.0), &[semitones(C4, 1.0)]), None, "C#4");
    }

    #[test]
    fn test_every_note_of_a_chord_is_detected() {
        let chord = mix(&[instrument_tone(C4, 0.1), instrument_tone(E4, 0.1), instrument_tone(G4, 0.1)]);
        let a = analyzed(&chord);
        let expected = [C4, E4, G4];
        for hz in expected {
            assert!(a.detect(hz, &expected).is_some(), "{hz} Hz missing from C major chord");
        }
    }

    #[test]
    fn test_wrong_note_is_rejected_inside_a_chord() {
        let chord = mix(&[instrument_tone(C4, 0.1), instrument_tone(E4, 0.1), instrument_tone(G4, 0.1)]);
        let a = analyzed(&chord);
        // Score expects C#4 / F#4 but the player plays C major.
        for wrong in [semitones(C4, 1.0), semitones(G4, -1.0)] {
            assert_eq!(a.detect(wrong, &[wrong, E4]), None, "{wrong} Hz falsely detected");
        }
    }

    #[test]
    fn test_low_e2_pitch_within_10_cents_and_f2_rejected() {
        const E2: f64 = 82.41;
        let a = analyzed(&instrument_tone(E2, 0.2));
        let hz = a.detect(E2, &[E2]).expect("E2 should be detected");
        assert!(cents(hz, E2).abs() < 10.0, "measured {hz} Hz ({:+.1} cents)", cents(hz, E2));
        assert_eq!(a.detect(semitones(E2, 1.0), &[semitones(E2, 1.0)]), None, "F2");
    }

    #[test]
    fn test_attack_level_scales_with_loudness() {
        let quiet = analyzed(&instrument_tone(C4, 0.05)).evidence(C4, &[C4]).unwrap().attack_level;
        let loud = analyzed(&instrument_tone(C4, 0.2)).evidence(C4, &[C4]).unwrap().attack_level;
        let ratio = loud / quiet;
        assert!((ratio - 4.0).abs() < 0.2, "4x amplitude should give 4x level, got {ratio}");
    }

    #[test]
    fn test_attack_level_hears_a_restrike_the_long_window_blurs() {
        // Same string ringing at 0.1, re-struck to 0.4 in the newest samples.
        let ringing = instrument_tone(C4, 0.1);
        let mut restruck = ringing.clone();
        let struck = instrument_tone(C4, 0.4);
        restruck[FFT_SIZE - ATTACK_WINDOW..].copy_from_slice(&struck[FFT_SIZE - ATTACK_WINDOW..]);
        let (before, after) = (analyzed(&ringing), analyzed(&restruck));
        let short_jump = after.evidence(C4, &[C4]).unwrap().attack_level / before.evidence(C4, &[C4]).unwrap().attack_level;
        assert!(short_jump > 3.5, "short window should see ~4x, got {short_jump}");
    }

    #[test]
    fn test_quiet_note_at_minus_50_dbfs_is_detected() {
        let a = analyzed(&instrument_tone(C4, 10f32.powf(-50.0 / 20.0)));
        assert!(a.detect(C4, &[C4]).is_some());
    }

    #[test]
    fn test_white_noise_and_silence_detect_nothing() {
        let mut seed = 12345u32;
        let noise: Vec<f32> = (0..FFT_SIZE)
            .map(|_| {
                seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
                (seed >> 8) as f32 / (1u32 << 24) as f32 - 0.5
            })
            .collect();
        for (name, frame) in [("noise", noise), ("silence", vec![0.0; FFT_SIZE])] {
            let a = analyzed(&frame);
            for hz in [C4, E4, G4, 440.0] {
                assert_eq!(a.detect(hz, &[hz]), None, "{name}: {hz} Hz falsely detected");
            }
        }
    }
}
