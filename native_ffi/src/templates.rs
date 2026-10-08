//! Note templates: what each note's harmonics look like on one instrument,
//! learned from notes played alone (a calibration scale), then used by the
//! joint fit (dsp.rs) to pull apart notes that share harmonics in a chord.
//!
//! Why it helps: an octave above C4 (C5) has every harmonic on one of C4's.
//! A free-shaped C4 can absorb all of C5. A C4 whose shape is KNOWN (say its
//! 2nd harmonic is 60% of its 1st) can only claim its share of the shared
//! peaks; whatever is left over must be C5.

use crate::dsp::{Analyzer, FFT_SIZE, HOP_SIZE};
use crate::models::Notes;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Harmonics per template (matches the joint fit's model, dsp::MAX_FIT_HARMONIC).
pub const TEMPLATE_HARMONICS: usize = 24;
/// Frames starting this soon after a note's onset still hold the strike's
/// broadband click, which isn't the note's timbre.
const SKIP_ATTACK_MS: f32 = 30.0;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct NoteTemplates {
    /// Which instrument these were learned on ("Piano", ...).
    pub instrument: String,
    /// MIDI note number -> relative strength of harmonics 1..=TEMPLATE_HARMONICS
    /// (sums to 1). Missing keys fall back to the joint fit's band model.
    pub profiles: BTreeMap<u8, Vec<f32>>,
}

fn midi_of(hz: f64) -> f64 {
    69.0 + 12.0 * (hz / 440.0).log2()
}

impl NoteTemplates {
    /// Template of the key nearest `hz`, if `hz` is within 50 cents of it.
    pub fn profile(&self, hz: f64) -> Option<&[f32]> {
        let m = midi_of(hz);
        let key = m.round();
        if (m - key).abs() >= 0.5 || !(0.0..=127.0).contains(&key) {
            return None;
        }
        self.profiles.get(&(key as u8)).map(Vec::as_slice)
    }

    /// Learns one template per key from `notes` played one at a time in
    /// `mono` (each key may be played several times, e.g. soft and loud;
    /// every strike counts equally).
    pub fn learn(instrument: &str, mono: &[f32], sample_rate: u32, notes: &[Notes]) -> Self {
        let ms = 1000.0 / sample_rate as f32;
        let mut analyzer = Analyzer::new(sample_rate);
        let mut sums: BTreeMap<u8, (Vec<f32>, u32)> = BTreeMap::new();
        for note in notes {
            let (Some(start), Some(end)) = (note.start_time_ms, note.end_time_ms) else { continue };
            let key = midi_of(note.pitch_hz).round();
            if !(0.0..=127.0).contains(&key) {
                continue;
            }
            // Frames lying wholly inside the held note, past the strike click.
            let first = ((start + SKIP_ATTACK_MS) / ms).ceil() as usize;
            let mut strike = vec![0.0f32; TEMPLATE_HARMONICS];
            let mut frames = 0;
            let mut pos = first;
            while pos + FFT_SIZE <= mono.len() && (pos + FFT_SIZE) as f32 * ms <= end {
                analyzer.analyze(&mono[pos..pos + FFT_SIZE]);
                for (acc, a) in strike.iter_mut().zip(analyzer.harmonic_amplitudes(note.pitch_hz, TEMPLATE_HARMONICS)) {
                    *acc += a;
                }
                frames += 1;
                pos += HOP_SIZE;
            }
            let total: f32 = strike.iter().sum();
            if frames == 0 || total <= 0.0 {
                continue;
            }
            let entry = sums.entry(key as u8).or_insert_with(|| (vec![0.0; TEMPLATE_HARMONICS], 0));
            for (acc, a) in entry.0.iter_mut().zip(&strike) {
                *acc += a / total;
            }
            entry.1 += 1;
        }
        let profiles = sums
            .into_iter()
            .map(|(key, (sum, count))| (key, sum.into_iter().map(|a| a / count as f32).collect()))
            .collect();
        Self { instrument: instrument.to_string(), profiles }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::PI;

    const SR: u32 = 44100;

    fn note(id: u64, midi: f64, start: f32, end: f32) -> Notes {
        Notes {
            note_id: id,
            pitch_hz: 440.0 * 2f64.powf((midi - 69.0) / 12.0),
            start_time_ms: Some(start),
            end_time_ms: Some(end),
            duration_ms: Some(end - start),
            is_end: false,
            vibrato_depth: None,
            pedal_action: None,
            has_accent: None,
            markings: None,
        }
    }

    /// Notes played one after another; harmonic k has amplitude `shape(k)`.
    fn render(notes: &[Notes], shape: impl Fn(usize) -> f64) -> Vec<f32> {
        let end = notes.iter().map(|n| n.end_time_ms.unwrap()).fold(0.0, f32::max);
        let mut out = vec![0.0f32; ((end / 1000.0 + 0.2) * SR as f32) as usize];
        for n in notes {
            let (s, e) = ((n.start_time_ms.unwrap() / 1000.0 * SR as f32) as usize, (n.end_time_ms.unwrap() / 1000.0 * SR as f32) as usize);
            for (i, x) in out[s..e].iter_mut().enumerate() {
                let t = i as f64 / SR as f64;
                *x += (1..=TEMPLATE_HARMONICS)
                    .filter(|&k| k as f64 * n.pitch_hz < 5000.0)
                    .map(|k| 0.1 * shape(k) * (2.0 * PI * k as f64 * n.pitch_hz * t).sin())
                    .sum::<f64>() as f32;
            }
        }
        out
    }

    #[test]
    fn test_learned_template_matches_the_played_harmonic_shape() {
        // C4 with harmonics falling as 1/k, struck soft and loud.
        let notes = [note(1, 60.0, 100.0, 800.0), note(2, 60.0, 1000.0, 1700.0)];
        let mut audio = render(&notes[..1], |k| 1.0 / k as f64);
        let loud = render(&notes, |k| 3.0 / k as f64);
        let s = (1000.0 / 1000.0 * SR as f32) as usize;
        audio.resize(loud.len(), 0.0);
        audio[s..].copy_from_slice(&loud[s..]);
        let t = NoteTemplates::learn("Piano", &audio, SR, &notes);
        let p = t.profile(261.63).expect("C4 learned");
        let expected: Vec<f64> = (1..=TEMPLATE_HARMONICS).filter(|&k| k as f64 * 261.63 < 5000.0).map(|k| 1.0 / k as f64).collect();
        let total: f64 = expected.iter().sum();
        for (k, (&got, want)) in p.iter().zip(expected.iter().map(|e| e / total)).enumerate() {
            assert!((got as f64 - want).abs() < 0.02, "harmonic {}: {got:.3} vs {want:.3}", k + 1);
        }
        assert!((p.iter().sum::<f32>() - 1.0).abs() < 1e-4);
    }

    #[test]
    fn test_profile_is_found_by_nearest_key_and_absent_keys_fall_back() {
        let t = NoteTemplates { instrument: "Piano".into(), profiles: BTreeMap::from([(69, vec![1.0; TEMPLATE_HARMONICS])]) };
        assert!(t.profile(440.0).is_some());
        assert!(t.profile(445.0).is_some(), "20 cents sharp is still A4");
        assert!(t.profile(466.16).is_none(), "A#4 has no template");
    }

    #[test]
    fn test_templates_survive_a_json_round_trip() {
        let t = NoteTemplates { instrument: "Piano".into(), profiles: BTreeMap::from([(60, vec![0.5, 0.25, 0.25])]) };
        let back: NoteTemplates = serde_json::from_str(&serde_json::to_string(&t).unwrap()).unwrap();
        assert_eq!(back, t);
    }
}
