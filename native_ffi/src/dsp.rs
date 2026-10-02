//! Score-informed note detection: "is this expected note sounding right now?"
//!
//! We never transcribe blindly. The score tells us which notes should be
//! sounding, so for each one we only ask whether its harmonic series stands out
//! (a) above the room's noise floor and (b) above the same series one semitone
//! higher and lower. Every frame is explained jointly by all expected notes and
//! their neighbours (joint.rs), so a neighbour can't borrow a chord mate's peaks.

use crate::joint;
use crate::templates::NoteTemplates;
use num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::cell::RefCell;
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
/// The joint fit models each note up to this harmonic: enough to explain the
/// peaks chord mates share, short of the weak, very sharp top of a piano string.
const MAX_FIT_HARMONIC: usize = 24;
/// First harmonic of each band with its own loudness in the joint fit. Real
/// instruments don't share one harmonic recipe (a piano bass has a weak
/// fundamental), so each band of a note is fitted separately.
const FIT_BANDS: [usize; 4] = [1, 3, 6, 11];
/// Harmonics of different notes closer than this (in bins) are one FFT peak.
const SLOT_MERGE_BINS: f64 = 1.0;
const FIT_ITERATIONS: usize = 100;
/// Harmonics judged are below this number. Around harmonic 17 a semitone
/// shift equals one harmonic spacing (17 × 6% ≈ 1), so the neighbour's comb
/// lands back on the note's own; real strings are also sharpest up there.
const MAX_JUDGED_HARMONIC: usize = 16;
/// Notes too low to reach MIN_SEMITONE_GAP_BINS anywhere (below ~E2 at
/// 44.1 kHz) use the harmonics at least this close to their best separation.
/// Known limit: below A#1 (58 Hz) even the best harmonics are ~2 bins from a
/// neighbour's, inside the window's blur; A0-A1 need a longer window.
const BEST_SEPARATION_SHARE: f64 = 0.8;
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
    /// The note's energy ÷ that of its strongest non-expected semitone
    /// neighbour, both from the frame's joint fit, at the note's
    /// well-separated harmonics. 1.0 = can't tell them apart; infinity = the
    /// neighbour explains nothing.
    pub dominance: f32,
    /// How strongly the note's harmonics sound in the newest ATTACK_WINDOW
    /// samples. Absolute scale is arbitrary; only ratios over time mean
    /// something (a re-pluck of a ringing string shows up as a jump, see tracker.rs).
    pub attack_level: f32,
    /// Fitted strength of the note ÷ that of the strongest note in the frame's
    /// joint fit (0..=1). A wrong note can win its neighbour comparison with a
    /// crumb of stray energy (an attack's noise); a played note is a real
    /// share of what sounds.
    pub share: f32,
    /// How sure the evidence source is that the note sounds (0..=1): the
    /// pitch network's activation (run_onnx.rs); 1 for this analyser.
    pub confidence: f32,
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
    /// Joint fit of the current frame, for the expected notes it was made for.
    fit: RefCell<Option<JointFit>>,
    /// Learned harmonic shapes of this instrument's notes, if calibrated.
    templates: Option<NoteTemplates>,
}

/// Every expected note and its semitone neighbours, fitted together.
struct JointFit {
    /// The expected notes this fit was computed for (cache key).
    expected: Vec<f64>,
    notes: Vec<f64>,
    /// Per note: fitted magnitude at each harmonic (index k; 0 unused).
    contrib: Vec<Vec<f32>>,
}

impl JointFit {
    fn index_of(&self, hz: f64) -> Option<usize> {
        self.notes.iter().position(|&n| cents(n, hz).abs() < 50.0)
    }

    /// Fitted magnitude of `note` summed over all its modelled harmonics.
    fn strength(&self, note: usize) -> f32 {
        self.contrib[note].iter().sum()
    }

    /// Fitted energy of `note` at harmonic numbers `ks`.
    fn energy(&self, note: usize, ks: &[usize]) -> f32 {
        ks.iter().filter_map(|&k| self.contrib[note].get(k)).sum()
    }
}

fn band(k: usize) -> usize {
    FIT_BANDS.iter().rposition(|&first| k >= first).unwrap_or(0)
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
            fit: RefCell::new(None),
            templates: None,
            fft,
            window,
            min_peak,
        }
    }

    /// Uses learned note shapes in the joint fit (None = generic band model).
    pub fn set_templates(&mut self, templates: Option<NoteTemplates>) {
        self.templates = templates;
        *self.fit.get_mut() = None;
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
        *self.fit.get_mut() = None;

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

    /// How far (in bins) harmonic `k` of each semitone neighbour of `hz` lands
    /// from the nearest harmonic of `hz` itself, whichever neighbour is closer.
    /// Not just from harmonic k: high up, the neighbour's k-th harmonic sits on
    /// the note's (k±1)-th, and then the neighbour gets credit for the note.
    fn neighbour_separation_bins(&self, hz: f64, k: usize) -> f64 {
        [-1.0, 1.0]
            .into_iter()
            .map(|semitones| {
                let x = k as f64 * 2f64.powf(semitones / 12.0); // in units of hz
                (x - x.round()).abs() * hz / self.bin_hz
            })
            .fold(f64::INFINITY, f64::min)
    }

    /// Harmonic numbers a note at `hz` is judged on: the first MAX_HARMONICS
    /// (up to MAX_JUDGED_HARMONIC) whose neighbours' harmonics sit at least
    /// MIN_SEMITONE_GAP_BINS from every harmonic of the note. Elsewhere a note
    /// and its neighbour share FFT peaks and can't be told apart. Low notes
    /// never reach that gap; they use their best-separated harmonics instead
    /// (C2: 7th to 10th; C4: 3rd to 10th, at 44.1 kHz).
    fn judged_harmonics(&self, hz: f64) -> impl Iterator<Item = usize> + '_ {
        let nyquist = self.bin_hz * (self.mags.len() - 2) as f64;
        let top = (1..=MAX_JUDGED_HARMONIC)
            .take_while(|&k| k as f64 * hz <= MAX_HARMONIC_HZ.min(nyquist))
            .last()
            .unwrap_or(0);
        let best = (1..=top).map(|k| self.neighbour_separation_bins(hz, k)).fold(0.0, f64::max);
        let needed = MIN_SEMITONE_GAP_BINS.min(BEST_SEPARATION_SHARE * best);
        (1..=top)
            .filter(move |&k| self.neighbour_separation_bins(hz, k) >= needed)
            .take(MAX_HARMONICS)
    }

    /// Harmonic peaks of a note judged at `note_hz`, evaluated at `hz` (the
    /// note itself or a semitone neighbour, so both use the same harmonic
    /// numbers): (harmonic number, bin, magnitude).
    fn harmonic_peaks(&self, note_hz: f64, hz: f64) -> impl Iterator<Item = (usize, usize, f32)> + '_ {
        let nyquist = self.bin_hz * (self.mags.len() - 2) as f64;
        self.judged_harmonics(note_hz)
            .take_while(move |&k| k as f64 * hz <= MAX_HARMONIC_HZ.min(nyquist))
            .filter_map(move |k| self.peak_near(k as f64 * hz).map(|(b, m)| (k, b, m)))
    }

    /// Magnitude observed at each slot (`slot_hz` sorted ascending). Only
    /// true local maxima count (the flank of a louder peak next door is that
    /// peak's energy), and each peak belongs to the ONE slot nearest its
    /// interpolated frequency: E4's fundamental must not also be F4's.
    fn observe_slots(&self, slot_hz: &[f64]) -> Vec<f32> {
        let mut observed = vec![0.0f32; slot_hz.len()];
        for (s, &hz) in slot_hz.iter().enumerate() {
            let centre = hz / self.bin_hz;
            let radius = (centre * (2f64.powf(SEARCH_CENTS / 1200.0) - 1.0)).max(1.0);
            let lo = ((centre - radius).round() as usize).max(1);
            let hi = ((centre + radius).round() as usize).min(self.mags.len() - 2);
            for b in lo..=hi {
                if self.mags[b] < self.mags[b - 1] || self.mags[b] < self.mags[b + 1] {
                    continue;
                }
                let peak_hz = self.interpolated_hz(b);
                let nearest = match slot_hz.binary_search_by(|x| x.total_cmp(&peak_hz)) {
                    Ok(i) => i,
                    Err(i) if i == 0 => 0,
                    Err(i) if i == slot_hz.len() => i - 1,
                    Err(i) => if peak_hz - slot_hz[i - 1] <= slot_hz[i] - peak_hz { i - 1 } else { i },
                };
                if nearest == s {
                    observed[s] = observed[s].max(self.mags[b]);
                }
            }
        }
        observed
    }

    /// Frequency of the peak at bin `b`, refined by parabolic interpolation
    /// on log magnitudes (accurate to a fraction of a bin with a Hann window).
    fn interpolated_hz(&self, b: usize) -> f64 {
        let ln = |i: usize| (self.mags[i].max(1e-12) as f64).ln();
        let (a, m, c) = (ln(b - 1), ln(b), ln(b + 1));
        let denom = a - 2.0 * m + c;
        let offset = if denom.abs() > 1e-12 { (0.5 * (a - c) / denom).clamp(-0.5, 0.5) } else { 0.0 };
        (b as f64 + offset) * self.bin_hz
    }

    /// Magnitude of harmonics 1..=n of `hz` in the last analysed frame: the
    /// strongest true local peak within SEARCH_CENTS of each (0 if none, or
    /// above MAX_HARMONIC_HZ). Used to learn note templates (templates.rs).
    pub fn harmonic_amplitudes(&self, hz: f64, n: usize) -> Vec<f32> {
        let top = self.top_hz();
        (1..=n)
            .map(|k| {
                let f = k as f64 * hz;
                if f > top {
                    return 0.0;
                }
                let centre = f / self.bin_hz;
                let radius = (centre * (2f64.powf(SEARCH_CENTS / 1200.0) - 1.0)).max(1.0);
                let lo = ((centre - radius).round() as usize).max(1);
                let hi = ((centre + radius).round() as usize).min(self.mags.len() - 2);
                (lo..=hi)
                    .filter(|&b| self.mags[b] >= self.mags[b - 1] && self.mags[b] >= self.mags[b + 1])
                    .map(|b| self.mags[b])
                    .fold(0.0, f32::max)
            })
            .collect()
    }

    fn top_hz(&self) -> f64 {
        MAX_HARMONIC_HZ.min(self.bin_hz * (self.mags.len() - 2) as f64)
    }

    /// Fits this frame with every expected note plus each one's semitone
    /// neighbours. Their harmonics become slots (harmonics of different notes
    /// within SLOT_MERGE_BINS share one), each slot observes the peak there,
    /// and each note-band is one atom of the fit.
    fn joint_fit(&self, expected: &[f64]) -> JointFit {
        let mut notes: Vec<f64> = Vec::new();
        for &e in expected {
            for semitones in [0.0, -1.0, 1.0] {
                let hz = e * 2f64.powf(semitones / 12.0);
                if !notes.iter().any(|&n| cents(n, hz).abs() < 50.0) {
                    notes.push(hz);
                }
            }
        }
        let top = self.top_hz();
        let mut harmonics: Vec<(f64, usize, usize)> = Vec::new(); // (hz, note, k)
        for (n, &hz) in notes.iter().enumerate() {
            for k in (1..=MAX_FIT_HARMONIC).take_while(|&k| k as f64 * hz <= top) {
                harmonics.push((k as f64 * hz, n, k));
            }
        }
        harmonics.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut slot_hz: Vec<f64> = Vec::new();
        let mut slot_of = vec![vec![None; MAX_FIT_HARMONIC + 1]; notes.len()];
        for &(hz, n, k) in &harmonics {
            if slot_hz.last().is_none_or(|&s| hz - s > SLOT_MERGE_BINS * self.bin_hz) {
                slot_hz.push(hz);
            }
            slot_of[n][k] = Some(slot_hz.len() - 1);
        }

        // Atom shapes (note, weight per harmonic). A calibrated note is its
        // learned shape plus a brighter variant (harder strikes are brighter);
        // otherwise four free bands.
        let mut shapes: Vec<(usize, Vec<f32>)> = Vec::new();
        for (n, &hz) in notes.iter().enumerate() {
            match self.templates.as_ref().and_then(|t| t.profile(hz)) {
                Some(profile) => {
                    let learned: Vec<f32> = (0..=MAX_FIT_HARMONIC)
                        .map(|k| if k == 0 { 0.0 } else { profile.get(k - 1).copied().unwrap_or(0.0) })
                        .collect();
                    let brighter = learned.iter().enumerate().map(|(k, w)| w * k as f32 / MAX_FIT_HARMONIC as f32).collect();
                    shapes.push((n, learned));
                    shapes.push((n, brighter));
                }
                None => {
                    for b in 0..FIT_BANDS.len() {
                        shapes.push((n, (0..=MAX_FIT_HARMONIC).map(|k| if k > 0 && band(k) == b { 1.0 } else { 0.0 }).collect()));
                    }
                }
            }
        }
        let atoms: Vec<Vec<(usize, f32)>> = shapes
            .iter()
            .map(|(n, w)| (1..=MAX_FIT_HARMONIC).filter_map(|k| slot_of[*n][k].filter(|_| w[k] > 0.0).map(|s| (s, w[k]))).collect())
            .collect();
        let observed = self.observe_slots(&slot_hz);
        let h = joint::fit(&observed, &atoms, FIT_ITERATIONS);
        let mut contrib = vec![vec![0.0f32; MAX_FIT_HARMONIC + 1]; notes.len()];
        for ((n, w), &ha) in shapes.iter().zip(&h) {
            for k in 1..=MAX_FIT_HARMONIC {
                if slot_of[*n][k].is_some() {
                    contrib[*n][k] += ha * w[k];
                }
            }
        }
        JointFit { expected: expected.to_vec(), notes, contrib }
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
        // One fit per frame and expected set, shared by every candidate.
        let mut key = expected_hz.to_vec();
        if !key.iter().any(|&e| cents(e, target_hz).abs() < 50.0) {
            key.push(target_hz);
        }
        let mut cache = self.fit.borrow_mut();
        if cache.as_ref().is_none_or(|f| f.expected != key) {
            *cache = Some(self.joint_fit(&key));
        }
        let fit = cache.as_ref().expect("just filled");
        // Compared at the target's well-separated harmonics, as before.
        let ks: Vec<usize> = self.judged_harmonics(target_hz).collect();
        let own = fit.index_of(target_hz).map_or(0.0, |i| fit.energy(i, &ks));
        let strongest_rival = [-1.0, 1.0]
            .into_iter()
            .map(|semitones| target_hz * 2f64.powf(semitones / 12.0))
            .filter(|&n| !expected_hz.iter().any(|&e| cents(e, n).abs() < 50.0))
            .filter_map(|n| fit.index_of(n))
            .map(|i| fit.energy(i, &ks))
            .fold(0.0, f32::max);
        let dominance = if strongest_rival > 0.0 { own / strongest_rival } else { f32::INFINITY };
        let strongest = (0..fit.notes.len()).map(|i| fit.strength(i)).fold(0.0, f32::max);
        let share = match fit.index_of(target_hz) {
            Some(i) if strongest > 0.0 => fit.strength(i) / strongest,
            _ => 0.0,
        };
        drop(cache);
        Some(Detection {
            pitch_hz: self.estimate_pitch(target_hz)?,
            dominance,
            attack_level: self.short.level(target_hz),
            share,
            confidence: 1.0,
        })
    }

    /// Refined pitch near `hz` in the last analysed frame, if it has a peak there.
    pub fn measured_pitch(&self, hz: f64) -> Option<f64> {
        self.estimate_pitch(hz)
    }

    /// Strength of `hz`'s harmonics in the newest ATTACK_WINDOW samples.
    pub fn attack_level(&self, hz: f64) -> f32 {
        self.short.level(hz)
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

    /// Piano-like string: 24 partials, amplitude 1/k, each sharpened by
    /// stiffness (f_k = k·f0·√(1 + B·k²)). B = 1e-4 matches the bass notes of
    /// the rendered piano set (+22 cents at partial 16).
    fn piano_tone(f0: f64, amplitude: f32, b: f64) -> Vec<f32> {
        (0..FFT_SIZE)
            .map(|i| {
                let t = i as f64 / SR as f64;
                (1..=24)
                    .map(|k| {
                        let fk = k as f64 * f0 * (1.0 + b * (k * k) as f64).sqrt();
                        amplitude / k as f32 * (2.0 * std::f64::consts::PI * fk * t).sin() as f32
                    })
                    .sum()
            })
            .collect()
    }

    #[test]
    fn test_low_piano_notes_beat_their_neighbours_enough_to_start() {
        use crate::tracker::START_DOMINANCE_SINGLE;
        // C2 and E2 were missed in the rendered piano set; A#1 is the lowest
        // note this window can separate (see BEST_SEPARATION_SHARE).
        let mut failures = Vec::new();
        for (name, f0) in [("A#1", 58.27), ("C2", 65.41), ("E2", 82.41)] {
            let a = analyzed(&piano_tone(f0, 0.2, 1e-4));
            let own = a.evidence(f0, &[f0]).map_or(0.0, |d| d.dominance);
            if own < START_DOMINANCE_SINGLE {
                failures.push(format!("{name}: dominance {own:.2} < {START_DOMINANCE_SINGLE}"));
            }
            for (n, label) in [(-1.0, "below"), (1.0, "above")] {
                let rival = semitones(f0, n);
                let d = a.evidence(rival, &[rival]).map_or(0.0, |d| d.dominance);
                if d >= SUSTAIN_FOR_TEST {
                    failures.push(format!("{name}: semitone {label} looks present (dominance {d:.2})"));
                }
            }
        }
        assert!(failures.is_empty(), "{failures:#?}");
    }

    #[test]
    fn test_inner_note_of_a_piano_chord_starts_and_its_neighbour_does_not() {
        use crate::tracker::START_DOMINANCE_CHORD;
        // C3-E3-G3 under E4 (rendered piano set): an inner chord note must
        // clear the chord start threshold, even with its piano-sharp partials.
        let (c3, e3, f3, g3, e4) = (130.81, 164.81, 174.61, 196.0, 329.63);
        let chord = mix(&[piano_tone(c3, 0.1, 1e-4), piano_tone(e3, 0.1, 1e-4), piano_tone(g3, 0.1, 1e-4), piano_tone(e4, 0.1, 1e-4)]);
        let a = analyzed(&chord);
        let played = a.evidence(e3, &[c3, e3, g3, e4]).map_or(0.0, |d| d.dominance);
        assert!(played >= START_DOMINANCE_CHORD, "E3 in its chord: dominance {played:.2} < {START_DOMINANCE_CHORD}");
        // Score wrongly expects F3 where E3 is played: still a wrong note.
        let wrong = a.evidence(f3, &[c3, f3, g3, e4]).map_or(0.0, |d| d.dominance);
        assert!(wrong < SUSTAIN_FOR_TEST, "F3 accepted in place of E3 (dominance {wrong:.2})");
    }

    #[test]
    fn test_chord_played_a_semitone_below_the_score_is_rejected() {
        // Played G2-B2-D3-F4, but the score has the whole chord a semitone up:
        // every expected note is wrong and none may be accepted.
        let (g2, b2, d3, f4) = (98.0, 123.47, 146.83, 349.23);
        let chord = mix(&[piano_tone(g2, 0.1, 1e-4), piano_tone(b2, 0.1, 1e-4), piano_tone(d3, 0.1, 1e-4), piano_tone(f4, 0.1, 1e-4)]);
        let a = analyzed(&chord);
        let up = |hz: f64| semitones(hz, 1.0);
        let score = [up(g2), up(b2), up(d3), up(f4)];
        for (name, hz) in [("G#2", up(g2)), ("C3", up(b2)), ("D#3", up(d3)), ("F#4", up(f4))] {
            let d = a.evidence(hz, &score).map_or(0.0, |d| d.dominance);
            assert!(d < SUSTAIN_FOR_TEST, "{name} accepted from a chord played a semitone lower (dominance {d:.2})");
        }
    }

    /// Below the tracker's lowest threshold: a neighbour that measures this
    /// can neither start nor keep a note going.
    const SUSTAIN_FOR_TEST: f32 = crate::tracker::SUSTAIN_DOMINANCE;

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




