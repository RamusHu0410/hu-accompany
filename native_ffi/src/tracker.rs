//! Per-note state machines: turn frame-by-frame "is it sounding?" answers into
//! one record per played note (start, end, duration, measured pitch).
//!
//! Each expected note has its own state, so chord notes and overlapping
//! (let-ring) notes never interfere with each other.

use crate::dsp::{cents, Detection};
use crate::models::{NoteState, Notes};
use std::collections::HashMap;

/// Detected frames before a note counts as started (5 hops ≈ 29 ms)...
pub const ON_FRAMES: u32 = 5;
/// ...out of the last ON_WINDOW frames (not necessarily in a row). Filters
/// clicks and speech that briefly line up with a note, while inside dense
/// chords a real note's evidence may flicker frame to frame. ON_WINDOW =
/// ON_FRAMES would mean "in a row". Tuned on rendered piano + dense
/// Rachmaninoff; held-out MAESTRO: 3-of-3 gave 98.0% found / 2.2% wrong,
/// 5-of-8 gives 97.6% / 0.8%.
pub const ON_WINDOW: u32 = 8;
/// Consecutive missing frames before a note counts as stopped. Bridges short
/// dropouts (reverb, vibrato, bow changes) so one note isn't split in two.
pub const OFF_FRAMES: u32 = 8;
/// Hysteresis, like a Schmitt trigger: a note must beat its rival semitone
/// neighbours by a START threshold to begin, but only by SUSTAIN_DOMINANCE to
/// keep sounding. The attack of a different note (broadband pluck) briefly
/// flatters wrong neighbours, so starting is strict; a real note fading
/// inside a chord would flicker on and off, so sustaining is lenient.
///
/// Starting is stricter for a lone note than inside a chord: chord notes'
/// harmonics overlap and inflate their rivals, so a correct chord note
/// measures lower dominance than the same note played alone.
/// Tuned on GuitarSet (tests/real_audio.rs).
pub const START_DOMINANCE_SINGLE: f32 = 2.5;
pub const START_DOMINANCE_CHORD: f32 = 1.7;
pub const SUSTAIN_DOMINANCE: f32 = 1.5;
/// To start, a note must also hold this share of the frame's strongest note
/// (dsp::Detection::share). Right after a key strike the window is mostly the
/// hammer's broadband click, and a wrong note can win its neighbour comparison
/// on that noise, but not with a real share of what sounds. Tuned on the
/// rendered piano, dense Rachmaninoff and GuitarSet sets: 0.2 kept recall,
/// 0.3 cost dense chords ~5 points; held-out MAESTRO: 96.5% found, 1.9% wrong.
pub const START_SHARE: f32 = 0.2;
/// A note is listened for from this long before its score start until this
/// long after its score end (players are never perfectly on time).
pub const TIMING_MARGIN_MS: f32 = 85.0;
/// Repeated notes of the same pitch share one harmonic series, so the
/// analyser can't tell a ringing note from its repeat. When a note's pitch is
/// already sounding as we start listening for it, and the score has an earlier
/// note of that pitch, the sound is that earlier note's tail. The repeat only
/// starts on a new attack: its level must rise this far above the quietest
/// level heard since listening began (1.5 ≈ +3.5 dB). Tuned on GuitarSet:
/// 1.2-2.0 barely differ for chords; below 1.5 more wrong solo notes pass.
pub const ATTACK_RATIO: f32 = 1.5;
/// Notes starting within this long of the score's first note open the piece
/// together (a chord, or a grace note): any of them may set the clock.
const OPENING_GROUP_MS: f32 = 50.0;
/// Heard frames from a note's first on, among which its start is stamped
/// (Thresholds::edge_relative): ~185 ms of neural frames, enough for the
/// attack to reach its peak.
const RISE_FRAMES: usize = 16;

/// Decision thresholds. They depend on where the evidence comes from: the
/// DSP analyser (a frame every 5.8 ms, dominance ratios of harmonic sums) or
/// the pitch network (a frame every 11.6 ms, per-key activations 0..1).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Thresholds {
    pub on_frames: u32,
    pub on_window: u32,
    pub off_frames: u32,
    pub start_dominance_single: f32,
    pub start_dominance_chord: f32,
    pub sustain_dominance: f32,
    pub start_share: f32,
    /// Minimum Detection::confidence to start / keep a note.
    pub start_confidence: f32,
    pub sustain_confidence: f32,
    /// A note's start and end are stamped where its confidence crosses this
    /// share of its own peak (0 = off: stamp the first frame that passed or
    /// failed the absolute rules). Those can't place the edges: the network
    /// starts to rise ~30 ms before a note does, and sustain_confidence sits
    /// at its output on silence, so the note only fails them once the release
    /// has fully faded, ~100 ms (in a room's noise: much more) after. Crossing
    /// the same level on both edges keeps the duration right, which the
    /// backend judges against the written one (15% off is a finding).
    /// Only the stamps change; notes start and close by the absolute rules,
    /// so a flickering note is not split in two.
    pub edge_relative: f32,
    /// Per-frame decay of the recent peak the end is measured against, so a note
    /// that dies away slowly is followed, and only a sharp drop (a release) ends it.
    pub peak_decay: f32,
}

impl Thresholds {
    /// For dsp::Analyzer evidence (the constants above).
    pub const DSP: Self = Self {
        on_frames: ON_FRAMES,
        on_window: ON_WINDOW,
        off_frames: OFF_FRAMES,
        start_dominance_single: START_DOMINANCE_SINGLE,
        start_dominance_chord: START_DOMINANCE_CHORD,
        sustain_dominance: SUSTAIN_DOMINANCE,
        start_share: START_SHARE,
        start_confidence: 0.0,
        sustain_confidence: 0.0,
        edge_relative: 0.0,
        peak_decay: 1.0,
    };
    /// For run_onnx::neural_evidence. From the offline prototype: a note is
    /// there when its key reads >= 0.15 and >= 1.5x each non-expected
    /// semitone neighbour, in 2 frames. sustain_relative/peak_decay: on six
    /// real MAESTRO piano clips the median end stamp went from +399 ms to
    /// +92 ms after the key release (onsets and recall unchanged); 0.5 gave
    /// +187, 0.8 started cutting held notes short.
    pub const NEURAL: Self = Self {
        on_frames: 2,
        on_window: 4,
        off_frames: 4,
        start_dominance_single: 1.5,
        start_dominance_chord: 1.5,
        sustain_dominance: 1.0,
        start_share: 0.0,
        start_confidence: 0.15,
        sustain_confidence: 0.1,
        edge_relative: 0.75,
        peak_decay: 0.984,
    };
}

/// Time span covered by one analysis frame.
///
/// A long window hears a note as soon as it enters the window's END and until
/// it leaves the window's START. So onsets are stamped with `end_ms` of the
/// first frame that hears the note, and offsets with `start_ms` of the first
/// frame that no longer does. Stamping both with the centre would stretch
/// every note by about half a window at each end.
#[derive(Clone, Copy, Debug, Default)]
pub struct Frame {
    pub start_ms: f32,
    pub end_ms: f32,
}

impl Frame {
    /// Zero-width frame (tests, or when window length doesn't matter).
    pub fn at(ms: f32) -> Self {
        Self { start_ms: ms, end_ms: ms }
    }
    pub fn centre_ms(&self) -> f32 {
        (self.start_ms + self.end_ms) / 2.0
    }
}

#[derive(Default)]
struct Track {
    state: Option<NoteState>, // None = Idle; Some(Playing) once confirmed
    /// Not yet started: whether it was heard in each recent frame (bit 0 =
    /// this frame), for the ON_FRAMES-of-ON_WINDOW start rule.
    recent: u32,
    absent_run: u32,
    first_present: Frame,
    /// First frame of the current run of frames that no longer read as a
    /// strong note (see Thresholds::edge_relative); None while it does.
    weak_since: Option<Frame>,
    pitches: Vec<f64>,
    /// Set on the first observation: the pitch was already ringing from an
    /// earlier same-pitch note, so only a re-attack may start this one.
    needs_attack: bool,
    /// Quietest level since listening began (0 once the pitch fell silent).
    min_level: f32,
    /// Recent peak of Detection::confidence while heard (see Thresholds::edge_relative).
    peak_confidence: f32,
    /// The first RISE_FRAMES heard frames of this candidate, with their confidence.
    rise: Vec<(Frame, f32)>,
}

/// How the score's clock relates to the stream's (sample 0 = mic opened).
#[derive(Clone, Copy, Debug, PartialEq)]
enum Clock {
    /// Score time = stream time.
    Stream,
    /// Score time 0 is wherever the player's first note starts. Until that
    /// note is heard, only the opening notes are listened for, at any time.
    AwaitingFirstNote,
    /// The first note was heard: score time = stream time - `offset_ms`.
    /// Tracks keep stream time; the offset is applied when a note is reported,
    /// so it can still be refined: `refine` is the first note, whose start
    /// is only stamped for good once its attack is over (RISE_FRAMES).
    Anchored { offset_ms: f32, refine: Option<usize> },
}

pub struct NoteTracker {
    notes: Vec<Notes>,
    /// Per note: stop listening for it (if not yet started) once the next
    /// same-pitch note's window opens, so one sound can't start both.
    handover_ms: Vec<f32>,
    /// Per note: the previous note of the same pitch, if any.
    predecessor: Vec<Option<usize>>,
    /// Per note: it was heard and has since stopped sounding (record closed).
    ended: Vec<bool>,
    tracks: HashMap<usize, Track>,
    th: Thresholds,
    clock: Clock,
}

impl NoteTracker {
    /// Notes without a score start time are ignored: we can't know when to listen.
    pub fn new(notes: &[Notes]) -> Self {
        Self::with_thresholds(notes, Thresholds::DSP)
    }

    pub fn with_thresholds(notes: &[Notes], th: Thresholds) -> Self {
        let mut notes: Vec<Notes> =
            notes.iter().filter(|n| n.start_time_ms.is_some()).cloned().collect();
        notes.sort_by(|a, b| a.start_time_ms.unwrap().total_cmp(&b.start_time_ms.unwrap()));

        let successor: Vec<Option<usize>> = (0..notes.len())
            .map(|i| (i + 1..notes.len()).find(|&j| cents(notes[j].pitch_hz, notes[i].pitch_hz).abs() < 50.0))
            .collect();
        let handover_ms = successor
            .iter()
            .map(|s| s.map_or(f32::INFINITY, |j| notes[j].start_time_ms.unwrap() - TIMING_MARGIN_MS))
            .collect();
        let mut predecessor = vec![None; notes.len()];
        for (i, s) in successor.iter().enumerate() {
            if let Some(j) = *s {
                predecessor[j] = Some(i);
            }
        }
        let ended = vec![false; notes.len()];
        Self { notes, handover_ms, predecessor, ended, tracks: HashMap::new(), th, clock: Clock::Stream }
    }

    /// Starts the score's clock when the player's first note is heard instead
    /// of at sample 0. The microphone opens before the player starts (a count-in,
    /// start-up latency), and by more than the +-85 ms the notes are matched
    /// within; on a 100 ms lead only 73% of onsets of real piano stayed inside
    /// their windows, on 200 ms recall fell from 95% to 58%.
    /// Everything sent in and out of the tracker is stream time and score time
    /// respectively: frames and `candidates(now)` take stream time, notes come
    /// back in score time.
    pub fn anchored(mut self) -> Self {
        if !self.notes.is_empty() {
            self.clock = Clock::AwaitingFirstNote;
        }
        self
    }

    /// Notes that open the piece (see OPENING_GROUP_MS).
    fn opening_notes(&self) -> Vec<usize> {
        let first = self.notes.first().and_then(|n| n.start_time_ms).unwrap_or(0.0);
        (0..self.notes.len())
            .filter(|&i| self.notes[i].start_time_ms.is_some_and(|s| s <= first + OPENING_GROUP_MS))
            .collect()
    }

    fn offset_ms(&self) -> f32 {
        match self.clock {
            Clock::Anchored { offset_ms, .. } => offset_ms,
            _ => 0.0,
        }
    }

    /// True once score time is known (always, unless waiting for the first note).
    pub fn has_clock(&self) -> bool {
        self.clock != Clock::AwaitingFirstNote
    }

    fn window(&self, i: usize) -> (f32, f32) {
        let n = &self.notes[i];
        let start = n.start_time_ms.unwrap();
        // No score end: listen for one margin's worth after the start.
        let end = n.end_time_ms.unwrap_or(start);
        (start - TIMING_MARGIN_MS, end + TIMING_MARGIN_MS)
    }

    fn is_playing(&self, i: usize) -> bool {
        matches!(self.tracks.get(&i).and_then(|t| t.state.as_ref()), Some(NoteState::Playing { .. }))
    }

    /// Earlier notes of the same pitch as `i`, most recent first.
    fn same_pitch_before(&self, i: usize) -> impl Iterator<Item = usize> + '_ {
        std::iter::successors(self.predecessor[i], |&p| self.predecessor[p])
    }

    /// Notes to test at `now_ms`: inside their score window (and not yet handed
    /// over to a repeat of the same pitch), or still sounding.
    pub fn candidates(&self, now_ms: f32) -> Vec<usize> {
        if self.clock == Clock::AwaitingFirstNote {
            return self.opening_notes();
        }
        let now_ms = now_ms - self.offset_ms();
        (0..self.notes.len())
            .filter(|&i| {
                let (open, close) = self.window(i);
                let listening = open <= now_ms && now_ms <= close && now_ms < self.handover_ms[i];
                listening || self.is_playing(i)
            })
            .collect()
    }

    pub fn pitch_hz(&self, i: usize) -> f64 {
        self.notes[i].pitch_hz
    }

    /// Feeds one frame (stream time). `observations` = (candidate index, the
    /// analyser's evidence for that note, if any). Returns notes that finished
    /// on this frame, in score time.
    pub fn update(&mut self, frame: Frame, observations: &[(usize, Option<Detection>)]) -> Vec<Notes> {
        let awaiting = self.clock == Clock::AwaitingFirstNote;
        let now_ms = frame.centre_ms() - self.offset_ms();
        // How many notes the score says are sounding right now (no margin).
        // Before the clock is set, the opening notes are.
        let polyphony = observations
            .iter()
            .filter(|&&(i, _)| {
                let n = &self.notes[i];
                awaiting
                    || (n.start_time_ms.is_some_and(|s| s <= now_ms)
                        && n.end_time_ms.is_some_and(|e| now_ms <= e))
            })
            .count();
        let th = self.th;
        let start_needed = if polyphony >= 2 { th.start_dominance_chord } else { th.start_dominance_single };
        let mut finished = Vec::new();
        let mut started = Vec::new();
        for &(i, evidence) in observations {
            let first_sight = !self.tracks.contains_key(&i);
            // Sound already present when listening starts is the earlier
            // same-pitch note's tail only if that note is still being heard,
            // or was never heard (a missed note can still ring). If it was
            // heard and has stopped, the sound is this note's own (played early).
            let earlier_still_sounding = self.same_pitch_before(i).any(|p| self.is_playing(p));
            let earlier_ended = self.predecessor[i].is_some_and(|p| self.ended[p]);
            let inherits_sound = first_sight
                && self.predecessor[i].is_some()
                && (earlier_still_sounding
                    || (!earlier_ended
                        && evidence.is_some_and(|d| d.dominance >= th.sustain_dominance && d.confidence >= th.sustain_confidence)));
            let track = self.tracks.entry(i).or_default();
            if first_sight {
                track.needs_attack = inherits_sound;
                track.min_level = f32::INFINITY;
            }
            let playing = track.state.is_some();
            let needed = if playing { th.sustain_dominance } else { start_needed };
            let share_needed = if playing { 0.0 } else { th.start_share };
            let confidence_needed = if playing { th.sustain_confidence } else { th.start_confidence };
            let mut heard = evidence
                .filter(|d| d.dominance >= needed && d.share >= share_needed && d.confidence >= confidence_needed)
                .map(|d| d.pitch_hz);
            let strong = heard.is_some()
                && evidence.is_some_and(|d| !playing || d.confidence >= th.edge_relative * track.peak_confidence);
            if let Some(d) = evidence.filter(|_| strong) {
                track.peak_confidence = (track.peak_confidence * th.peak_decay).max(d.confidence);
            }
            if playing {
                match (strong, track.weak_since) {
                    (true, _) => track.weak_since = None,
                    (false, None) => track.weak_since = Some(frame),
                    _ => {}
                }
            }
            if track.state.is_none() && track.needs_attack {
                let level = evidence.map_or(0.0, |d| d.attack_level);
                track.min_level = track.min_level.min(level);
                if level < ATTACK_RATIO * track.min_level {
                    heard = None; // still the earlier note's tail
                }
            }
            match heard {
                Some(hz) => {
                    let window = (1u32 << th.on_window) - 1;
                    if track.recent & window == 0 && track.state.is_none() {
                        track.first_present = frame; // a new candidate begins
                        track.pitches.clear();
                        track.peak_confidence = 0.0;
                        track.rise.clear();
                    }
                    if track.rise.len() < RISE_FRAMES {
                        track.rise.push((frame, evidence.map_or(0.0, |d| d.confidence)));
                    }
                    track.recent = (track.recent << 1) | 1;
                    track.absent_run = 0;
                    track.pitches.push(hz);
                    if track.state.is_none() && (track.recent & window).count_ones() >= th.on_frames {
                        track.state = Some(NoteState::Playing { start_ms: track.first_present.end_ms });
                        started.push((i, track.first_present.end_ms));
                    }
                }
                None => {
                    if track.state.is_none() {
                        track.recent <<= 1; // a blip that never confirms ages out of the window
                        continue;
                    }
                    track.absent_run += 1;
                    if track.absent_run >= th.off_frames {
                        finished.extend(self.close(i, frame));
                    }
                }
            }
        }
        if awaiting {
            // The first note: score time 0 is where it was scored to start.
            if let Some(&(i, heard_ms)) = started.iter().min_by(|a, b| a.1.total_cmp(&b.1)) {
                let offset_ms = heard_ms - self.notes[i].start_time_ms.unwrap();
                self.clock = Clock::Anchored { offset_ms, refine: (th.edge_relative > 0.0).then_some(i) };
            }
        } else if let Clock::Anchored { refine: Some(i), .. } = self.clock {
            // Once the first note's attack is over its start is known better.
            let attack_over = self.tracks.get(&i).is_none_or(|t| t.rise.len() >= RISE_FRAMES);
            if attack_over {
                let heard_ms = self.tracks.get(&i).map(|t| self.onset_ms(t, t.first_present.end_ms));
                let offset_ms = heard_ms.map(|h| h - self.notes[i].start_time_ms.unwrap());
                self.clock = Clock::Anchored { offset_ms: offset_ms.unwrap_or(self.offset_ms()), refine: None };
            }
        }
        // A re-attack ends the earlier same-pitch note(s) still ringing: the
        // string was struck again, at a moment we measured.
        for (i, start_ms) in started {
            let ringing: Vec<usize> = self.same_pitch_before(i).filter(|&p| self.is_playing(p)).collect();
            for p in ringing {
                finished.extend(self.close(p, Frame::at(start_ms)));
            }
        }
        finished
    }

    /// Where a note started (stream time): the first frame at `edge_relative`
    /// of its attack's peak, or `first` (the first frame to hear it) when that is off.
    fn onset_ms(&self, track: &Track, first: f32) -> f32 {
        let peak = track.rise.iter().map(|&(_, c)| c).fold(0.0, f32::max);
        track
            .rise
            .iter()
            .find(|&&(_, c)| c >= self.th.edge_relative * peak)
            .filter(|_| self.th.edge_relative > 0.0)
            .map_or(first, |&(f, _)| f.end_ms)
            .max(first)
    }

    /// End of stream (recording stopped): close every note still sounding.
    pub fn finish(&mut self, now_ms: f32) -> Vec<Notes> {
        let mut playing: Vec<usize> = (0..self.notes.len()).filter(|&i| self.is_playing(i)).collect();
        playing.sort();
        playing.into_iter().filter_map(|i| self.close(i, Frame::at(now_ms))).collect()
    }

    /// `ended` = when the note is known to have stopped; the end is stamped
    /// earlier if it had already faded (`weak_since`). Frames are stream
    /// time; the note comes out in score time.
    fn close(&mut self, i: usize, ended: Frame) -> Option<Notes> {
        let track = self.tracks.remove(&i)?;
        let Some(NoteState::Playing { start_ms }) = track.state else {
            return None;
        };
        self.ended[i] = true;
        let ended = track.weak_since.filter(|w| w.start_ms < ended.start_ms).unwrap_or(ended);
        let start_ms = self.onset_ms(&track, start_ms);
        let offset = self.offset_ms();
        let mut end_ms = ended.start_ms;
        let mut start_ms = start_ms;
        if end_ms <= start_ms {
            // Sounds shorter than the window (or only heard once they filled
            // much of it) make the edge stamps cross. For those the frame
            // centres are the better estimate.
            start_ms = track.first_present.centre_ms();
            end_ms = ended.centre_ms();
            if end_ms <= start_ms {
                return None;
            }
        }
        let mut pitches = track.pitches;
        pitches.sort_by(f64::total_cmp);
        let note = &self.notes[i];
        Some(Notes {
            note_id: note.note_id,
            pitch_hz: pitches[pitches.len() / 2], // median: robust to attack transients
            start_time_ms: Some(start_ms - offset),
            end_time_ms: Some(end_ms - offset),
            duration_ms: Some(end_ms - start_ms),
            is_end: note.is_end,
            vibrato_depth: None,
            pedal_action: None,
            has_accent: None,
            markings: None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const HOP_MS: f32 = 5.0;

    /// Evidence with no rival at all.
    fn certain(pitch_hz: f64) -> Detection {
        Detection { pitch_hz, dominance: f32::INFINITY, attack_level: 1.0, share: 1.0, confidence: 1.0 }
    }

    fn note(id: u64, hz: f64, start: f32, end: f32) -> Notes {
        Notes {
            note_id: id,
            pitch_hz: hz,
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

    /// Drives the tracker from `from_ms` to `to_ms`; `sounding(i, t)` says
    /// whether note i is heard at time t (measured at its score pitch).
    fn run(
        tracker: &mut NoteTracker,
        from_ms: f32,
        to_ms: f32,
        sounding: impl Fn(usize, f32) -> bool,
    ) -> Vec<Notes> {
        let mut out = Vec::new();
        let mut t = from_ms;
        while t < to_ms {
            let obs: Vec<(usize, Option<Detection>)> = tracker
                .candidates(t)
                .into_iter()
                .map(|i| (i, sounding(i, t).then(|| certain(tracker.pitch_hz(i)))))
                .collect();
            out.extend(tracker.update(Frame::at(t), &obs));
            t += HOP_MS;
        }
        out
    }

    #[test]
    fn test_one_record_per_played_note() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let out = run(&mut tr, 0.0, 1000.0, |_, t| (0.0..500.0).contains(&t));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].start_time_ms, Some(0.0));
        assert_eq!(out[0].end_time_ms, Some(500.0));
        assert_eq!(out[0].pitch_hz, 440.0);
    }

    #[test]
    fn test_short_dropout_does_not_split_a_note() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        // 3 missing frames (15 ms) in the middle, e.g. a reverb flicker.
        let out = run(&mut tr, 0.0, 1000.0, |_, t| (0.0..500.0).contains(&t) && !(200.0..215.0).contains(&t));
        assert_eq!(out.len(), 1, "dropout split the note: {out:?}");
    }

    #[test]
    fn test_flickering_note_starts_but_a_brief_click_does_not() {
        // Heard 2 frames of every 3 (inside a dense chord): starts, stamped
        // at its first frame. Heard ON_FRAMES - 1 frames then gone: ignored.
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 1000.0), note(2, 554.37, 0.0, 1000.0)]);
        let mut out = run(&mut tr, 0.0, 1500.0, |i, t| {
            let frame = (t / HOP_MS) as u32;
            match i {
                0 => (100.0..600.0).contains(&t) && (frame - 20) % 3 != 2,
                _ => frame >= 20 && frame < 20 + ON_FRAMES - 1,
            }
        });
        out.extend(tr.finish(1500.0));
        let ids: Vec<u64> = out.iter().map(|n| n.note_id).collect();
        assert_eq!(ids, vec![1], "{out:?}");
        assert_eq!(out[0].start_time_ms, Some(100.0));
    }

    #[test]
    fn test_blip_shorter_than_on_frames_is_ignored() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let out = run(&mut tr, 0.0, 1000.0, |_, t| (100.0..110.0).contains(&t)); // 2 frames
        assert!(out.is_empty(), "blip reported as a note: {out:?}");
    }

    #[test]
    fn test_weak_evidence_cannot_start_a_note_but_can_sustain_one() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 1000.0)]);
        let between = (SUSTAIN_DOMINANCE + START_DOMINANCE_SINGLE) / 2.0;
        let mut out = Vec::new();
        let mut t = 0.0;
        while t < 1000.0 {
            let dominance = match t {
                t if t < 100.0 => between,          // like a wrong-neighbour pluck: must not start
                t if t < 200.0 => START_DOMINANCE_SINGLE, // clear note: starts
                t if t < 400.0 => between,          // fading in a chord: keeps going
                _ => 0.0,                           // gone
            };
            let obs = [(0, Some(Detection { pitch_hz: 440.0, dominance, attack_level: 1.0, share: 1.0, confidence: 1.0 }))];
            out.extend(tr.update(Frame::at(t), &obs));
            t += HOP_MS;
        }
        assert_eq!(out.len(), 1, "{out:?}");
        assert_eq!(out[0].start_time_ms, Some(100.0));
        assert_eq!(out[0].end_time_ms, Some(400.0));
    }

    #[test]
    fn test_a_crumb_of_energy_cannot_start_a_note_but_a_real_share_can_sustain_it() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 1000.0)]);
        let mut out = Vec::new();
        let mut t = 0.0;
        while t < 1000.0 {
            let share = match t {
                t if t < 100.0 => START_SHARE / 2.0, // onset click: wins its neighbours, holds a crumb
                t if t < 200.0 => START_SHARE,       // real note: starts
                t if t < 400.0 => START_SHARE / 2.0, // quieter than its chord mates: keeps going
                _ => 0.0,
            };
            let obs = [(0, (share > 0.0).then_some(Detection { pitch_hz: 440.0, dominance: f32::INFINITY, attack_level: 1.0, share, confidence: 1.0 }))];
            out.extend(tr.update(Frame::at(t), &obs));
            t += HOP_MS;
        }
        assert_eq!(out.len(), 1, "{out:?}");
        assert_eq!((out[0].start_time_ms, out[0].end_time_ms), (Some(100.0), Some(400.0)));
    }

    #[test]
    fn test_chord_notes_start_on_weaker_evidence_than_lone_notes() {
        let dominance = (START_DOMINANCE_CHORD + START_DOMINANCE_SINGLE) / 2.0;
        let evidence = Some(Detection { pitch_hz: 440.0, dominance, attack_level: 1.0, share: 1.0, confidence: 1.0 });
        let started = |notes: &[Notes]| {
            let mut tr = NoteTracker::new(notes);
            let obs: Vec<_> = (0..notes.len()).map(|i| (i, evidence)).collect();
            let mut t = 0.0;
            while t < 300.0 {
                tr.update(Frame::at(t), &obs);
                t += HOP_MS;
            }
            tr.finish(300.0).len()
        };
        assert_eq!(started(&[note(1, 440.0, 0.0, 500.0)]), 0, "lone note needs stronger evidence");
        let chord = [note(1, 440.0, 0.0, 500.0), note(2, 554.37, 0.0, 500.0)];
        assert_eq!(started(&chord), 2, "chord notes start on this evidence");
    }

    /// Frames like the real pipeline's: 93 ms long, 5 ms apart.
    fn run_real_frames(tracker: &mut NoteTracker, heard: impl Fn(Frame) -> bool) -> Vec<Notes> {
        let mut out = Vec::new();
        let mut t = 0.0;
        while t < 1000.0 {
            let frame = Frame { start_ms: t, end_ms: t + 93.0 };
            out.extend(tracker.update(frame, &[(0, heard(frame).then_some(certain(440.0)))]));
            t += HOP_MS;
        }
        out.extend(tracker.finish(1000.0));
        out
    }

    #[test]
    fn test_short_sound_gets_edge_stamps() {
        // Heard as soon as it touches the window: edges give the true times.
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let out = run_real_frames(&mut tr, |f| f.start_ms < 260.0 && f.end_ms > 200.0);
        assert_eq!(out.len(), 1, "{out:?}");
        assert_eq!((out[0].start_time_ms, out[0].end_time_ms), (Some(203.0), Some(260.0)));
    }

    #[test]
    fn test_crossed_edge_stamps_fall_back_to_centres() {
        // Only heard while near the window centre (190-230 ms): edge stamps
        // would put the end before the start. Never send that to the backend.
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let out = run_real_frames(&mut tr, |f| (190.0..230.0).contains(&f.centre_ms()));
        assert_eq!(out.len(), 1, "{out:?}");
        let (start, end) = (out[0].start_time_ms.unwrap(), out[0].end_time_ms.unwrap());
        assert!(end > start, "end before start: {:?}", out[0]);
        assert!((start - 190.0).abs() <= HOP_MS && (end - 230.0).abs() <= HOP_MS, "{start}-{end}");
    }

    #[test]
    fn test_chord_notes_are_tracked_independently() {
        let chord = [note(1, 261.63, 0.0, 500.0), note(2, 329.63, 0.0, 500.0), note(3, 392.0, 0.0, 500.0)];
        let mut tr = NoteTracker::new(&chord);
        // Note 2 is released early; the others ring on.
        let out = run(&mut tr, 0.0, 1000.0, |i, t| t < if i == 1 { 250.0 } else { 500.0 });
        let ends: HashMap<u64, f32> = out.iter().map(|n| (n.note_id, n.end_time_ms.unwrap())).collect();
        assert_eq!(ends, HashMap::from([(1, 500.0), (2, 250.0), (3, 500.0)]));
    }

    #[test]
    fn test_note_held_past_its_score_window_keeps_sounding() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let out = run(&mut tr, 0.0, 2000.0, |_, t| t < 1200.0);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].end_time_ms, Some(1200.0), "held-too-long duration must be kept");
    }

    /// Drives the tracker with one pitch whose loudness follows `level(t)`
    /// (0 = not heard). Every candidate sees the same evidence, as in the real
    /// pipeline: same-pitch notes share one harmonic series.
    fn run_levels(tracker: &mut NoteTracker, to_ms: f32, level: impl Fn(f32) -> f32) -> Vec<Notes> {
        let mut out = Vec::new();
        let mut t = 0.0;
        while t < to_ms {
            let l = level(t);
            let evidence = (l > 0.0).then_some(Detection { pitch_hz: 440.0, dominance: f32::INFINITY, attack_level: l, share: 1.0, confidence: 1.0 });
            let obs: Vec<_> = tracker.candidates(t).into_iter().map(|i| (i, evidence)).collect();
            out.extend(tracker.update(Frame::at(t), &obs));
            t += HOP_MS;
        }
        out.extend(tracker.finish(to_ms));
        out
    }

    /// A plucked string: full level at `at_ms`, decaying ~9 dB per 250 ms.
    fn pluck(t: f32, at_ms: f32) -> f32 {
        if t < at_ms { 0.0 } else { (-(t - at_ms) / 400.0).exp() }
    }

    fn times(n: &Notes) -> (u64, f32, f32) {
        (n.note_id, n.start_time_ms.unwrap(), n.end_time_ms.unwrap())
    }

    #[test]
    fn test_ringing_note_is_not_stolen_by_next_same_pitch_note() {
        // Note 2 is re-plucked 100 ms late, while note 1 still rings.
        let notes = [note(1, 440.0, 0.0, 500.0), note(2, 440.0, 500.0, 1000.0)];
        let mut tr = NoteTracker::new(&notes);
        let out = run_levels(&mut tr, 1500.0, |t| if t < 600.0 { pluck(t, 0.0) } else if t < 1100.0 { pluck(t, 600.0) } else { 0.0 });
        let got: Vec<_> = out.iter().map(times).collect();
        // Note 2 starts at its re-pluck, not when its window opened (415 ms),
        // and note 1 ends at that same, measured moment.
        assert_eq!(got, vec![(1, 0.0, 600.0), (2, 600.0, 1100.0)]);
    }

    #[test]
    fn test_held_note_without_replay_is_one_record() {
        // The player lets note 1 ring through note 2's slot and never re-plucks:
        // that is what happened, so that is what we report.
        let notes = [note(1, 440.0, 0.0, 500.0), note(2, 440.0, 500.0, 1000.0)];
        let mut tr = NoteTracker::new(&notes);
        let out = run_levels(&mut tr, 1500.0, |t| if t < 1000.0 { pluck(t, 0.0) } else { 0.0 });
        let got: Vec<_> = out.iter().map(times).collect();
        assert_eq!(got, vec![(1, 0.0, 1000.0)]);
    }

    #[test]
    fn test_repeat_after_silence_starts_without_needing_an_attack_jump() {
        // Note 1 dies out before note 2's window opens (415 ms).
        let notes = [note(1, 440.0, 0.0, 300.0), note(2, 440.0, 500.0, 1000.0)];
        let mut tr = NoteTracker::new(&notes);
        let out = run_levels(&mut tr, 1500.0, |t| match t {
            t if t < 300.0 => 1.0,
            t if (520.0..1000.0).contains(&t) => 0.2, // quiet, flat: no jump at all
            _ => 0.0,
        });
        let got: Vec<_> = out.iter().map(times).collect();
        assert_eq!(got, vec![(1, 0.0, 300.0), (2, 520.0, 1000.0)]);
    }

    #[test]
    fn test_early_repeat_after_the_earlier_note_ended_starts_without_an_attack_jump() {
        // Note 1 is heard and ends at 300 ms (piano damper). Note 2 is played
        // 100 ms early, so it already sounds when its window opens (415 ms):
        // that sound is note 2's own, not note 1's tail.
        let notes = [note(1, 440.0, 0.0, 300.0), note(2, 440.0, 500.0, 1000.0)];
        let mut tr = NoteTracker::new(&notes);
        let out = run_levels(&mut tr, 1500.0, |t| match t {
            t if t < 300.0 => 1.0,
            t if (400.0..1000.0).contains(&t) => 1.0, // flat: no jump after 415 ms
            _ => 0.0,
        });
        let got: Vec<_> = out.iter().map(times).collect();
        assert_eq!(got, vec![(1, 0.0, 300.0), (2, 415.0, 1000.0)]);
    }

    #[test]
    fn test_missed_predecessor_tail_is_not_credited_to_next_note() {
        // Note 1 sounds but outside its own window (never detected); its tail is
        // still ringing when note 2's window opens. Note 2 must wait for its pluck.
        let notes = [note(1, 440.0, 2000.0, 2100.0), note(2, 440.0, 2500.0, 3000.0)];
        let mut tr = NoteTracker::new(&notes);
        let out = run_levels(&mut tr, 3500.0, |t| if t < 2600.0 { pluck(t, 1000.0) * 3.0 } else if t < 3100.0 { pluck(t, 2600.0) } else { 0.0 });
        let starts: Vec<_> = out.iter().filter(|n| n.note_id == 2).map(|n| n.start_time_ms.unwrap()).collect();
        assert_eq!(starts, vec![2600.0]);
    }

    #[test]
    fn test_finish_closes_notes_still_sounding() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        assert!(run(&mut tr, 0.0, 300.0, |_, _| true).is_empty());
        let out = tr.finish(300.0);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].end_time_ms, Some(300.0));
    }

    #[test]
    fn test_unplayed_note_emits_nothing() {
        let mut tr = NoteTracker::new(&[note(1, 440.0, 0.0, 500.0)]);
        let mut out = run(&mut tr, 0.0, 1000.0, |_, _| false);
        out.extend(tr.finish(1000.0));
        assert!(out.is_empty());
    }

    /// Frames like the neural pipeline's (11.6 ms) with a chosen confidence.
    fn run_confidence(th: Thresholds, to_ms: f32, confidence: impl Fn(f32) -> f32) -> Vec<Notes> {
        let mut tr = NoteTracker::with_thresholds(&[note(1, 440.0, 0.0, 1000.0)], th);
        let mut out = Vec::new();
        let mut t = 0.0;
        while t < to_ms {
            let c = confidence(t);
            let evidence = (c > 0.0).then_some(Detection { pitch_hz: 440.0, dominance: f32::INFINITY, attack_level: 1.0, share: 1.0, confidence: c });
            out.extend(tr.update(Frame::at(t), &[(0, evidence)]));
            t += 11.6;
        }
        out.extend(tr.finish(to_ms));
        out
    }

    #[test]
    fn test_end_is_stamped_where_the_level_fell_not_where_it_vanished() {
        // Plays at 0.8, is released at 500 ms and fades to 0.1 by 600 ms, then
        // stays there: a room's noise keeps the key above the absolute
        // sustain threshold, so the note only closes when recording stops.
        let level = |t: f32| match t {
            t if t < 500.0 => 0.8,
            t if t < 600.0 => 0.8 - 0.7 * (t - 500.0) / 100.0,
            _ => 0.1,
        };
        let out = run_confidence(Thresholds::NEURAL, 2000.0, level);
        assert_eq!(out.len(), 1, "{out:?}");
        // It crossed 75% of its peak (0.6) at ~529 ms.
        let end = out[0].end_time_ms.unwrap();
        assert!((end - 529.0).abs() <= 12.0, "ended at {end}");

        // Without the relative rule the same input ends when recording stops.
        let out = run_confidence(Thresholds::DSP, 2000.0, level);
        assert!(out[0].end_time_ms.unwrap() > 1900.0, "{out:?}");
    }

    #[test]
    fn test_a_dip_inside_a_note_does_not_end_it_early() {
        // 45 ms at 40% of the level, in the middle of a held note.
        let level = |t: f32| match t {
            t if t < 1000.0 && !(400.0..445.0).contains(&t) => 0.8,
            t if t < 1000.0 => 0.32,
            _ => 0.0,
        };
        let out = run_confidence(Thresholds::NEURAL, 1500.0, level);
        assert_eq!(out.len(), 1, "split by the dip: {out:?}");
        let end = out[0].end_time_ms.unwrap();
        assert!((end - 1000.0).abs() <= 12.0, "ended at {end}");
    }

    #[test]
    fn test_a_slowly_dying_note_is_followed_to_its_release() {
        // A held piano note loses ~3 dB per second; the release at 1500 ms is
        // the only sharp drop.
        let level = |t: f32| if t < 1500.0 { 0.8 * (-t / 1500.0).exp() } else { 0.0 };
        let out = run_confidence(Thresholds::NEURAL, 2500.0, level);
        assert_eq!(out.len(), 1, "{out:?}");
        let end = out[0].end_time_ms.unwrap();
        assert!((end - 1500.0).abs() <= 25.0, "ended at {end}");
    }

    /// A line of three notes at score times 0-500, 500-1000, 1000-1500 ms.
    fn three_notes() -> Vec<Notes> {
        vec![note(1, 440.0, 0.0, 500.0), note(2, 554.37, 500.0, 1000.0), note(3, 659.26, 1000.0, 1500.0)]
    }

    /// The player plays the three notes `lead_ms` after the stream began,
    /// each `late_ms[i]` later than written.
    fn play_three(tr: &mut NoteTracker, lead_ms: f32, late_ms: [f32; 3]) -> Vec<Notes> {
        let mut out = run(tr, 0.0, 4000.0, |i, t| {
            let start = lead_ms + i as f32 * 500.0 + late_ms[i];
            (start..start + 450.0).contains(&t)
        });
        out.extend(tr.finish(4000.0));
        out
    }

    #[test]
    fn test_without_the_anchor_a_mic_opened_early_loses_the_score() {
        let mut tr = NoteTracker::new(&three_notes());
        let out = play_three(&mut tr, 700.0, [0.0; 3]);
        let starts: Vec<f32> = out.iter().map(|n| n.start_time_ms.unwrap()).collect();
        assert_ne!(starts, vec![0.0, 500.0, 1000.0], "stream time is what it is: {out:?}");
    }

    #[test]
    fn test_anchored_clock_starts_at_the_first_note_whenever_it_is_played() {
        for lead_ms in [0.0, 85.0, 300.0, 700.0, 2500.0] {
            let mut tr = NoteTracker::new(&three_notes()).anchored();
            let out = play_three(&mut tr, lead_ms, [0.0; 3]);
            let got: Vec<_> = out.iter().map(times).collect();
            assert_eq!(got, vec![(1, 0.0, 450.0), (2, 500.0, 950.0), (3, 1000.0, 1450.0)], "lead {lead_ms}");
        }
    }

    #[test]
    fn test_anchored_clock_keeps_the_players_rhythm_after_the_first_note() {
        // Note 2 is 60 ms late and note 3 40 ms early: that is what is reported.
        let mut tr = NoteTracker::new(&three_notes()).anchored();
        let out = play_three(&mut tr, 700.0, [0.0, 60.0, -40.0]);
        let starts: Vec<f32> = out.iter().map(|n| n.start_time_ms.unwrap()).collect();
        assert_eq!(starts, vec![0.0, 560.0, 960.0], "{out:?}");
    }

    #[test]
    fn test_anchor_uses_the_first_notes_scored_start_not_zero() {
        // A piece that opens with a rest: first note scored at 400 ms.
        let notes = [note(1, 440.0, 400.0, 900.0), note(2, 554.37, 900.0, 1400.0)];
        let mut tr = NoteTracker::new(&notes).anchored();
        let mut out = run(&mut tr, 0.0, 4000.0, |i, t| {
            let start = 1200.0 + i as f32 * 500.0;
            (start..start + 450.0).contains(&t)
        });
        out.extend(tr.finish(4000.0));
        let got: Vec<_> = out.iter().map(times).collect();
        assert_eq!(got, vec![(1, 400.0, 850.0), (2, 900.0, 1350.0)]);
    }

    #[test]
    fn test_anchored_tracker_waits_for_the_first_note_and_ignores_the_rest() {
        let mut tr = NoteTracker::new(&three_notes()).anchored();
        // Only note 2's pitch sounds for the first 2 s: no clock, no notes.
        let out = run(&mut tr, 0.0, 2000.0, |i, t| i == 1 && (300.0..800.0).contains(&t));
        assert!(out.is_empty(), "{out:?}");
        assert!(!tr.has_clock());
        assert_eq!(tr.candidates(5000.0), vec![0], "listens for the opening note, at any time");
        // Now the real first note.
        let out = run(&mut tr, 2000.0, 2600.0, |i, t| i == 0 && (2100.0..2500.0).contains(&t));
        assert!(tr.has_clock());
        assert_eq!(out.iter().map(times).collect::<Vec<_>>(), vec![(1, 0.0, 400.0)]);
    }

    #[test]
    fn test_chord_opening_a_piece_sets_the_clock_from_whichever_note_is_heard_first() {
        let notes = [note(1, 261.63, 0.0, 500.0), note(2, 329.63, 0.0, 500.0), note(3, 392.0, 500.0, 1000.0)];
        let mut tr = NoteTracker::new(&notes).anchored();
        assert_eq!(tr.candidates(0.0), vec![0, 1]);
        // Note 2 speaks first, note 1 follows 20 ms later.
        let mut out = run(&mut tr, 0.0, 3000.0, |i, t| match i {
            0 => (1020.0..1450.0).contains(&t),
            1 => (1000.0..1450.0).contains(&t),
            _ => (1500.0..1950.0).contains(&t),
        });
        out.extend(tr.finish(3000.0));
        let by_id: HashMap<u64, (f32, f32)> = out.iter().map(|n| (n.note_id, (n.start_time_ms.unwrap(), n.end_time_ms.unwrap()))).collect();
        assert_eq!(by_id[&2], (0.0, 450.0));
        assert_eq!(by_id[&1], (20.0, 450.0));
        assert_eq!(by_id[&3], (500.0, 950.0));
    }

    #[test]
    fn test_anchored_finish_closes_a_note_still_sounding_in_score_time() {
        let mut tr = NoteTracker::new(&three_notes()).anchored();
        run(&mut tr, 0.0, 1500.0, |i, t| i == 0 && t >= 700.0);
        let out = tr.finish(1500.0);
        // Started at stream 700 = score 0; stopped at stream 1500 = score 800.
        assert_eq!(out.iter().map(times).collect::<Vec<_>>(), vec![(1, 0.0, 800.0)]);
    }

    #[test]
    fn test_anchored_finish_before_any_note_is_heard_reports_nothing() {
        let mut tr = NoteTracker::new(&three_notes()).anchored();
        assert!(tr.finish(3000.0).is_empty());
    }
}
