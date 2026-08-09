use cpal::Stream;
use serde::{Deserialize, Serialize};
use std::ops::Range;

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub enum Instrument {
    Violin,
    Viola,
    Cello,
    Piano,
    Guitar,
    Trumpet,
    FrenchHorn,
    Clarinet
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct InstrumentProfile {
    pub instrument_type : Instrument,
    pub freq_rng : Range<f32>,
    pub chords : bool
}

#[derive(Debug, Clone, Deserialize)]
pub struct TimingSpecs {
    pub bpm: f32,
    pub beat_unit: u32 
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Notes {
    pub note_id: u64,
    pub pitch_hz: f64,
    pub start_time_ms: Option<f32>, // temporary
    pub end_time_ms: Option<f32>, // temporary
    pub duration_ms: Option<f32>, // temporary

    // Optional Members
    pub vibrato_depth: Option<f32>,
    pub pedal_action: Option<String>,
    pub has_accent: Option<bool>,
    pub markings: Option<String>
}

#[derive(Debug, Deserialize, Clone)]
pub struct PieceData {
    pub piece_name: String,
    pub curr_phase: u8,
    pub instrument: Option<Instrument>,
    pub curr_music_phrase: u32,
    pub timing: TimingSpecs,
    pub notes: Vec<Notes>
}

#[derive(Debug, Clone, PartialEq)]
pub enum NoteState {
    Idle,
    Playing { start_ms: f32 },
}

#[derive(Debug)]
pub struct NoteResult {
    pub start_ms: f32,
    pub end_ms: f32,
    pub duration_ms: f32,
}

pub struct NoteDetector {
    pub state: NoteState,
    pub target_hz: f32,
    pub threshold: f32,
    pub consecutive_high_frames: u32,
    pub consecutive_low_frames: u32,
    pub required_frames: u32, // e.g., 2 or 3
}


pub struct SendStream(pub Stream);

unsafe impl Send for SendStream {}
