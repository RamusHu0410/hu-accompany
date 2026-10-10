//! How loudly a note was played, as a number the rest of the app can compare.
//!
//! `volume` is 0.0 (at or below `FLOOR_DBFS`) to 1.0 (full scale), spaced in
//! decibels, not in raw amplitude. Loudness is perceived logarithmically: a
//! linear scale would squash all quiet playing (a pianissimo 40 dB down is
//! only 0.01 of full amplitude) into a sliver next to zero, leaving no
//! resolution exactly where dynamics are subtle.
//!
//! It is relative to this microphone and device, not calibrated sound
//! pressure: the same hand on the same piano reads differently on another
//! phone or at another distance. Turning a volume into pp..ff is done later
//! in the Python backend, where the score's dynamic markings are known.

/// Level that maps to volume 0.0. Quieter than this is indistinguishable
/// from room noise on a phone microphone.
pub const FLOOR_DBFS: f32 = -60.0;

/// Length of the window the loudness is measured over, and how far it moves
/// between measurements.
const WINDOW_MS: f32 = 50.0;
const HOP_MS: f32 = 25.0;

fn window_samples(sample_rate: u32) -> usize {
    ((WINDOW_MS / 1000.0 * sample_rate as f32).round() as usize).max(1)
}

fn hop_samples(sample_rate: u32) -> usize {
    ((HOP_MS / 1000.0 * sample_rate as f32).round() as usize).max(1)
}

/// RMS level in dBFS, AES17 convention: 0 dB is the RMS of a full-scale sine
/// (so a full-scale sine reads 0, not -3). Empty or silent input is
/// `NEG_INFINITY`. A sample that is not a finite number counts as silence
/// rather than poisoning the whole measurement.
pub fn rms_dbfs(samples: &[f32]) -> f32 {
    if samples.is_empty() {
        return f32::NEG_INFINITY;
    }
    let sum_of_squares: f64 = samples.iter().filter(|s| s.is_finite()).map(|&s| (s as f64) * (s as f64)).sum();
    let rms = (sum_of_squares / samples.len() as f64).sqrt();
    if rms == 0.0 {
        return f32::NEG_INFINITY;
    }
    (20.0 * (rms * std::f64::consts::SQRT_2).log10()) as f32
}

/// Maps a level in dBFS onto 0.0..=1.0, linearly in dB between `FLOOR_DBFS`
/// and 0 dBFS. Louder than full scale (clipping) is 1.0; NaN and silence are 0.0.
pub fn db_to_volume(db: f32) -> f32 {
    if db.is_nan() {
        return 0.0;
    }
    ((db - FLOOR_DBFS) / -FLOOR_DBFS).clamp(0.0, 1.0)
}

/// The volume of one note, from that note's audio.
///
/// It is the loudest 50 ms window, not the average over the note: a piano
/// note decays and a short staccato note is mostly silence, so an average
/// would rate how long the note rang, not how hard it was played. A clip
/// shorter than one window is measured whole. Empty audio is 0.0.
pub fn note_volume(samples: &[f32], sample_rate: u32) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let window = window_samples(sample_rate);
    let hop = hop_samples(sample_rate);
    if samples.len() <= window {
        return db_to_volume(rms_dbfs(samples));
    }

    let mut loudest = f32::NEG_INFINITY;
    let mut start = 0;
    while start + window <= samples.len() {
        loudest = loudest.max(rms_dbfs(&samples[start..start + window]));
        start += hop;
    }
    // The hop may not land on the end: always look at the final window too.
    loudest = loudest.max(rms_dbfs(&samples[samples.len() - window..]));
    db_to_volume(loudest)
}

/// A running record of how loud the microphone was, for the whole recording.
///
/// A note is reported some time after it ends, and by then the raw audio of a
/// long note's attack (its loudest part) has been discarded. So the loudness is
/// logged as the audio arrives (one measurement per `HOP_MS`) and a note's
/// volume is looked up afterwards from its time span.
pub struct LevelLog {
    window: usize,
    hop: usize,
    sample_rate: u32,
    /// Samples not yet covered by a complete window.
    pending: Vec<f32>,
    /// `levels[i]` is the dBFS of the window that starts at sample `i * hop`.
    levels: Vec<f32>,
}

impl LevelLog {
    pub fn new(sample_rate: u32) -> Self {
        Self {
            window: window_samples(sample_rate),
            hop: hop_samples(sample_rate),
            sample_rate,
            pending: Vec::new(),
            levels: Vec::new(),
        }
    }

    /// Adds the next chunk of the recording, in order, at any chunk size.
    pub fn push(&mut self, chunk: &[f32]) {
        self.pending.extend_from_slice(chunk);
        while self.pending.len() >= self.window {
            self.levels.push(rms_dbfs(&self.pending[..self.window]));
            self.pending.drain(..self.hop);
        }
    }

    /// Volume of the loudest window that overlaps `from_ms..to_ms`
    /// (milliseconds from the first sample), or `None` if no window has been
    /// completed there yet. A span that starts before the recording is clipped
    /// to its start; an empty span is looked up at its instant.
    pub fn peak_volume(&self, from_ms: f32, to_ms: f32) -> Option<f32> {
        let to_sample = |ms: f32| (ms.max(0.0) / 1000.0 * self.sample_rate as f32).round() as usize;
        let from = to_sample(from_ms);
        let to = to_sample(to_ms).max(from + 1);
        // Window i covers [i * hop, i * hop + window): it overlaps the span
        // when it starts before `to` and ends after `from`.
        let first = if from >= self.window { (from - self.window) / self.hop + 1 } else { 0 };
        let last_exclusive = to.div_ceil(self.hop).min(self.levels.len());
        let loudest = self.levels.get(first..last_exclusive)?.iter().copied().reduce(f32::max)?;
        Some(db_to_volume(loudest))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `ms` of a sine wave at `hz`, peak amplitude `amp`, at `rate`.
    fn sine(amp: f32, hz: f32, rate: u32, ms: f32) -> Vec<f32> {
        let n = (rate as f32 * ms / 1000.0) as usize;
        (0..n)
            .map(|i| amp * (2.0 * std::f32::consts::PI * hz * i as f32 / rate as f32).sin())
            .collect()
    }

    fn close(actual: f32, expected: f32, tolerance: f32) {
        assert!((actual - expected).abs() <= tolerance, "expected {expected} ± {tolerance}, got {actual}");
    }

    #[test]
    fn test_silence_is_volume_zero() {
        assert_eq!(note_volume(&vec![0.0; 48_000], 48_000), 0.0);
    }

    #[test]
    fn test_empty_clip_is_volume_zero() {
        assert_eq!(note_volume(&[], 48_000), 0.0);
        assert_eq!(rms_dbfs(&[]), f32::NEG_INFINITY);
    }

    #[test]
    fn test_full_scale_sine_is_volume_one() {
        close(note_volume(&sine(1.0, 440.0, 48_000, 1000.0), 48_000), 1.0, 0.01);
    }

    #[test]
    fn test_a_full_scale_sine_is_zero_dbfs() {
        close(rms_dbfs(&sine(1.0, 440.0, 48_000, 1000.0)), 0.0, 0.05);
    }

    #[test]
    fn test_minus_20_dbfs_is_two_thirds() {
        // amplitude 0.1 = -20 dBFS; (-20 - -60) / 60 = 0.667
        close(note_volume(&sine(0.1, 440.0, 48_000, 1000.0), 48_000), 0.667, 0.01);
    }

    #[test]
    fn test_halving_the_amplitude_lowers_volume_by_six_db_worth() {
        let loud = note_volume(&sine(0.4, 440.0, 48_000, 1000.0), 48_000);
        let soft = note_volume(&sine(0.2, 440.0, 48_000, 1000.0), 48_000);
        close(loud - soft, 6.02 / 60.0, 0.01);
    }

    #[test]
    fn test_below_the_floor_is_volume_zero() {
        assert_eq!(note_volume(&sine(1e-5, 440.0, 48_000, 1000.0), 48_000), 0.0);
    }

    #[test]
    fn test_over_range_input_is_capped_at_one() {
        assert_eq!(note_volume(&sine(4.0, 440.0, 48_000, 1000.0), 48_000), 1.0);
    }

    #[test]
    fn test_sample_rate_does_not_change_the_volume() {
        let a = note_volume(&sine(0.3, 440.0, 44_100, 1000.0), 44_100);
        let b = note_volume(&sine(0.3, 440.0, 48_000, 1000.0), 48_000);
        close(a, b, 0.01);
    }

    #[test]
    fn test_a_short_burst_is_judged_by_its_peak_not_diluted_by_the_silence_around_it() {
        let rate = 48_000;
        let burst = sine(0.5, 440.0, rate, 100.0);
        let silence = vec![0.0f32; (rate as f32 * 0.45) as usize];
        let clip: Vec<f32> = [silence.clone(), burst.clone(), silence].concat();

        let embedded = note_volume(&clip, rate);
        let alone = note_volume(&burst, rate);
        let diluted = db_to_volume(rms_dbfs(&clip));

        close(embedded, alone, 0.02);
        assert!(embedded > 0.5, "got {embedded}");
        assert!(embedded > diluted + 0.1, "peak {embedded} should clearly beat the whole-clip average {diluted}");
    }

    #[test]
    fn test_a_clip_shorter_than_one_window_still_gets_a_volume() {
        // 20 ms is shorter than the 50 ms window.
        close(note_volume(&sine(0.1, 440.0, 48_000, 20.0), 48_000), 0.667, 0.02);
    }

    #[test]
    fn test_non_finite_samples_are_treated_as_silence() {
        let mut clip = sine(0.1, 440.0, 48_000, 200.0);
        clip[10] = f32::NAN;
        clip[20] = f32::INFINITY;
        let v = note_volume(&clip, 48_000);
        assert!(v.is_finite() && (0.0..=1.0).contains(&v), "got {v}");
        // Two bad samples out of ~9600 must not change the level materially.
        close(v, 0.667, 0.02);
    }

    #[test]
    fn test_db_to_volume_edges() {
        assert_eq!(db_to_volume(FLOOR_DBFS), 0.0);
        assert_eq!(db_to_volume(0.0), 1.0);
        assert_eq!(db_to_volume(f32::NEG_INFINITY), 0.0);
        assert_eq!(db_to_volume(f32::NAN), 0.0);
        assert_eq!(db_to_volume(12.0), 1.0);
    }

    /// Feeds `clip` to a log in 512-sample chunks, like the microphone callback.
    fn logged(clip: &[f32], rate: u32) -> LevelLog {
        let mut log = LevelLog::new(rate);
        for chunk in clip.chunks(512) {
            log.push(chunk);
        }
        log
    }

    #[test]
    fn test_log_agrees_with_note_volume_over_the_whole_clip() {
        let clip = sine(0.1, 440.0, 48_000, 1000.0);
        let log = logged(&clip, 48_000);
        close(log.peak_volume(0.0, 1000.0).unwrap(), note_volume(&clip, 48_000), 0.01);
    }

    #[test]
    fn test_chunk_size_does_not_change_the_log() {
        let clip = sine(0.3, 440.0, 48_000, 700.0);
        let mut whole = LevelLog::new(48_000);
        whole.push(&clip);
        let chunked = logged(&clip, 48_000);
        assert!(whole.peak_volume(0.0, 700.0).is_some());
        assert_eq!(whole.peak_volume(0.0, 700.0), chunked.peak_volume(0.0, 700.0));
        assert_eq!(whole.peak_volume(200.0, 300.0), chunked.peak_volume(200.0, 300.0));
    }

    #[test]
    fn test_each_time_span_gets_its_own_volume() {
        // 500 ms at -26 dBFS (amplitude 0.05), then 500 ms at -6 dBFS (0.5).
        let clip = [sine(0.05, 440.0, 48_000, 500.0), sine(0.5, 440.0, 48_000, 500.0)].concat();
        let log = logged(&clip, 48_000);
        close(log.peak_volume(100.0, 400.0).unwrap(), db_to_volume(-26.02), 0.02);
        close(log.peak_volume(600.0, 900.0).unwrap(), db_to_volume(-6.02), 0.02);
    }

    #[test]
    fn test_a_decaying_note_is_judged_by_its_attack() {
        let rate = 48_000;
        let clip: Vec<f32> = sine(1.0, 440.0, rate, 2000.0)
            .iter()
            .enumerate()
            .map(|(i, s)| s * 0.5 * (-(i as f32) / rate as f32 * 3.0).exp())
            .collect();
        let log = logged(&clip, rate);
        let whole = log.peak_volume(0.0, 2000.0).unwrap();
        let tail = log.peak_volume(1500.0, 2000.0).unwrap();
        assert!(whole > tail + 0.5, "attack {whole} should be far above the faded tail {tail}");
        close(whole, db_to_volume(-6.6), 0.03);
    }

    #[test]
    fn test_the_start_of_a_long_recording_is_still_there_at_the_end() {
        // The reason for logging as the audio arrives: 10 s later, the loud
        // first 100 ms must still be answerable.
        let rate = 48_000;
        let mut clip = sine(0.5, 440.0, rate, 100.0);
        clip.extend(sine(0.01, 440.0, rate, 9_900.0));
        let log = logged(&clip, rate);
        close(log.peak_volume(0.0, 100.0).unwrap(), db_to_volume(-6.02), 0.03);
    }

    #[test]
    fn test_asking_beyond_the_recording_gives_none() {
        let log = logged(&sine(0.1, 440.0, 48_000, 500.0), 48_000);
        assert_eq!(log.peak_volume(2000.0, 2500.0), None);
        assert_eq!(LevelLog::new(48_000).peak_volume(0.0, 100.0), None);
    }

    #[test]
    fn test_silence_logs_as_volume_zero() {
        let log = logged(&vec![0.0; 24_000], 48_000);
        assert_eq!(log.peak_volume(0.0, 500.0), Some(0.0));
    }

    #[test]
    fn test_a_span_starting_before_the_first_sample_is_clamped() {
        let log = logged(&sine(0.1, 440.0, 48_000, 500.0), 48_000);
        close(log.peak_volume(-50.0, 100.0).unwrap(), db_to_volume(-20.0), 0.02);
    }

    #[test]
    fn test_a_span_ending_just_inside_a_loud_sound_sees_the_window_that_holds_it() {
        // A burst from 550 ms. A span ending at 551 ms overlaps the window that
        // starts at 550 ms (all burst, -6 dBFS) and the one at 525 ms (half
        // burst, ~3 dB lower). The span's last window must not be dropped.
        let rate = 48_000;
        let mut clip = vec![0.0f32; (rate as f32 * 0.55) as usize];
        clip.extend(sine(0.5, 440.0, rate, 100.0));
        clip.extend(vec![0.0f32; rate as usize / 2]);
        let log = logged(&clip, rate);
        close(log.peak_volume(0.0, 551.0).unwrap(), db_to_volume(-6.02), 0.02);
    }

    #[test]
    fn test_an_empty_span_is_looked_up_at_its_instant() {
        let log = logged(&sine(0.1, 440.0, 48_000, 500.0), 48_000);
        close(log.peak_volume(300.0, 300.0).unwrap(), db_to_volume(-20.0), 0.02);
    }
}
