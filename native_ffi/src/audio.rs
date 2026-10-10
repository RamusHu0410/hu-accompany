use crate::dsp::{Analyzer, Detection, FFT_SIZE, HOP_SIZE};
use crate::models::Notes;
use crate::run_onnx::{neural_evidence, NetFrame, StreamingPitchNet, FRAME_MS};
use crate::tracker::{Frame, NoteTracker, Thresholds};
use crate::volume::LevelLog;
use crate::templates::NoteTemplates;
use crate::{lock, ACTIVE_PIECE, ANCHOR_CLOCK, NOTES_SINK, NOTE_TEMPLATES, PIECE_GENERATION, USE_NEURAL, USER_DATA};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, Sample, SizedSample, Stream};
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::mpsc::{sync_channel, Receiver, RecvTimeoutError, SyncSender, TrySendError};
use std::sync::Mutex;
use std::time::Duration;

// ---- Status: how the capture side tells Dart what went wrong ----

pub const AUDIO_OK: i32 = 0;
/// The device has no microphone, or the OS hides it (permission denied on some platforms).
pub const AUDIO_ERR_NO_DEVICE: i32 = 1;
/// The microphone's input format could not be read.
pub const AUDIO_ERR_CONFIG: i32 = 2;
/// The microphone delivers a sample format we cannot convert.
pub const AUDIO_ERR_FORMAT: i32 = 3;
/// The OS refused to open the microphone (busy, no permission, no audio session).
pub const AUDIO_ERR_OPEN: i32 = 4;
/// The microphone opened but would not start.
pub const AUDIO_ERR_START: i32 = 5;
/// The audio stream failed while recording (device unplugged, route change).
pub const AUDIO_ERR_STREAM: i32 = 6;
/// Processing fell so far behind that audio had to be dropped: times after this are wrong.
pub const AUDIO_ERR_OVERRUN: i32 = 7;
/// The processing thread failed, or the previous one has not finished.
pub const AUDIO_ERR_WORKER: i32 = 8;
/// The stream stopped delivering audio (interruption, device went to sleep).
pub const AUDIO_ERR_STALLED: i32 = 9;
/// Codes from here on are warnings: audio is still being analysed.
pub const AUDIO_WARN_SILENT_INPUT: i32 = 100;
pub const AUDIO_WARN_NO_PITCH_NET: i32 = 101;

static STATUS_CODE: AtomicI32 = AtomicI32::new(AUDIO_OK);
static STATUS_MESSAGE: Mutex<String> = Mutex::new(String::new());

/// Records a problem for Dart to read (`audio_status`). A warning never
/// replaces an error. Not for the audio callback: it takes a lock.
pub fn report(code: i32, message: impl Into<String>) {
    let message = message.into();
    eprintln!("audio [{code}]: {message}");
    let replaced = STATUS_CODE.fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
        (code < AUDIO_WARN_SILENT_INPUT || current == AUDIO_OK || current >= AUDIO_WARN_SILENT_INPUT).then_some(code)
    });
    if replaced.is_ok() {
        *lock(&STATUS_MESSAGE) = message;
    }
}

/// Like `report`, without a message and without locking, for the audio callback.
fn report_from_callback(code: i32) {
    let _ = STATUS_CODE.fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
        (current == AUDIO_OK || current >= AUDIO_WARN_SILENT_INPUT).then_some(code)
    });
}

/// Forgets a problem that went away (audio resumed).
fn clear_if(code: i32) {
    if STATUS_CODE.compare_exchange(code, AUDIO_OK, Ordering::AcqRel, Ordering::Acquire).is_ok() {
        lock(&STATUS_MESSAGE).clear();
    }
}

pub fn clear_status() {
    STATUS_CODE.store(AUDIO_OK, Ordering::Release);
    lock(&STATUS_MESSAGE).clear();
}

pub fn status() -> i32 {
    STATUS_CODE.load(Ordering::Acquire)
}

pub fn status_message() -> String {
    let message = lock(&STATUS_MESSAGE).clone();
    if !message.is_empty() {
        return message;
    }
    match status() {
        AUDIO_OK => "",
        AUDIO_ERR_OVERRUN => "audio processing fell behind; part of the recording was dropped",
        _ => "unknown audio error",
    }
    .to_string()
}

#[derive(Debug)]
pub struct AudioError {
    pub code: i32,
    pub message: String,
}

impl AudioError {
    fn new(code: i32, message: impl Into<String>) -> Self {
        Self { code, message: message.into() }
    }
}

impl std::fmt::Display for AudioError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for AudioError {}

// ---- Capture ----

/// Averages each interleaved frame (L, R, L, R, ...) into one mono sample.
/// Treating interleaved stereo as mono would double the apparent sample rate
/// and halve every detected pitch.
pub fn downmix_to_mono(interleaved: &[f32], channels: usize) -> Vec<f32> {
    let mut mono = Vec::with_capacity(interleaved.len() / channels.max(1));
    downmix_into(&mut mono, interleaved, channels);
    mono
}

/// `downmix_to_mono` for any sample type the device may deliver, appending to
/// `out` (which keeps its capacity, so the audio callback need not allocate).
pub fn downmix_into<T: Sample>(out: &mut Vec<f32>, interleaved: &[T], channels: usize)
where
    f32: FromSample<T>,
{
    if channels <= 1 {
        out.extend(interleaved.iter().map(|&s| f32::from_sample(s)));
        return;
    }
    out.extend(interleaved.chunks_exact(channels).map(|frame| {
        frame.iter().map(|&s| f32::from_sample(s)).sum::<f32>() / channels as f32
    }));
}

/// Mono chunks queued between the capture callback and the processing thread.
/// ~2048 callbacks is 12-24 s of audio: far more than the processing thread
/// is ever behind, but a hard limit, so a stuck thread cannot eat the memory.
const QUEUE_CHUNKS: usize = 2048;
/// Chunk buffers circulating between the two threads, so the callback reuses
/// them instead of allocating (a callback is ~512-4096 frames).
const POOL_CHUNKS: usize = 64;
const CHUNK_CAPACITY: usize = 4096;

/// The capture callback's half of the link to the processing thread. It
/// never blocks and, once the pool is warm, never allocates.
struct ChunkSink {
    tx: SyncSender<Vec<f32>>,
    pool: Receiver<Vec<f32>>,
    channels: usize,
}

impl ChunkSink {
    fn push<T: Sample>(&mut self, data: &[T])
    where
        f32: FromSample<T>,
    {
        let mut chunk = self.pool.try_recv().unwrap_or_default();
        chunk.clear();
        downmix_into(&mut chunk, data, self.channels);
        match self.tx.try_send(chunk) {
            Ok(()) | Err(TrySendError::Disconnected(_)) => {}
            Err(TrySendError::Full(_)) => report_from_callback(AUDIO_ERR_OVERRUN),
        }
    }
}

/// An open microphone and the ends of its channels.
pub struct Capture {
    /// Dropping it turns the microphone off and closes `chunks`.
    pub stream: Stream,
    /// The device's real rate, which the processing loop needs for pitch and timing.
    pub sample_rate: u32,
    /// Mono samples at `sample_rate`.
    pub chunks: Receiver<Vec<f32>>,
    /// Give emptied chunks back here (see `start_processing_loop_with`).
    pub recycle: SyncSender<Vec<f32>>,
}

impl Capture {
    /// Opens the default microphone. Never panics: a panic over FFI aborts the app.
    pub fn open() -> Result<Self, AudioError> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or_else(|| AudioError::new(AUDIO_ERR_NO_DEVICE, "no microphone found"))?;
        let supported = device
            .default_input_config()
            .map_err(|e| AudioError::new(AUDIO_ERR_CONFIG, format!("could not read the microphone's format: {e}")))?;
        let sample_rate = supported.sample_rate().0;
        let channels = supported.channels() as usize;
        if channels == 0 || sample_rate == 0 {
            return Err(AudioError::new(AUDIO_ERR_CONFIG, format!("the microphone reports {channels} channels at {sample_rate} Hz")));
        }
        let format = supported.sample_format();
        let config: cpal::StreamConfig = supported.into();

        let (tx, chunks) = sync_channel(QUEUE_CHUNKS);
        let (recycle, pool) = sync_channel(POOL_CHUNKS);
        for _ in 0..POOL_CHUNKS {
            let _ = recycle.try_send(Vec::with_capacity(CHUNK_CAPACITY));
        }
        let sink = ChunkSink { tx, pool, channels };

        use cpal::SampleFormat as F;
        let stream = match format {
            F::F32 => build::<f32>(&device, &config, sink),
            F::I16 => build::<i16>(&device, &config, sink),
            F::U16 => build::<u16>(&device, &config, sink),
            F::I32 => build::<i32>(&device, &config, sink),
            F::F64 => build::<f64>(&device, &config, sink),
            F::I8 => build::<i8>(&device, &config, sink),
            F::U8 => build::<u8>(&device, &config, sink),
            F::U32 => build::<u32>(&device, &config, sink),
            F::I64 => build::<i64>(&device, &config, sink),
            F::U64 => build::<u64>(&device, &config, sink),
            other => Err(AudioError::new(AUDIO_ERR_FORMAT, format!("unsupported microphone sample format {other:?}"))),
        }?;
        stream
            .play()
            .map_err(|e| AudioError::new(AUDIO_ERR_START, format!("the microphone would not start: {e}")))?;
        Ok(Self { stream, sample_rate, chunks, recycle })
    }
}

fn build<T: SizedSample + Send + 'static>(
    device: &cpal::Device,
    config: &cpal::StreamConfig,
    mut sink: ChunkSink,
) -> Result<Stream, AudioError>
where
    f32: FromSample<T>,
{
    device
        .build_input_stream(
            config,
            move |data: &[T], _: &cpal::InputCallbackInfo| sink.push(data),
            |err| report(AUDIO_ERR_STREAM, format!("the audio stream failed: {err}")),
            None,
        )
        .map_err(|e| AudioError::new(AUDIO_ERR_OPEN, format!("could not open the microphone: {e}")))
}

// ---- Processing ----

/// The processing thread's half of the link: receives chunks, returns their
/// buffers, and notices a microphone that is silent or no longer delivering.
struct Intake {
    rx: Receiver<Vec<f32>>,
    recycle: Option<SyncSender<Vec<f32>>>,
    sample_rate: u32,
    /// Samples in a row that were exactly 0.0.
    zero_run: usize,
    stall_timeout: Duration,
}

/// A live microphone always has some noise; this long of exact zeros means the
/// OS is feeding silence (microphone permission denied, hardware muted).
const SILENT_INPUT_S: usize = 1;
const STALL_TIMEOUT: Duration = Duration::from_secs(2);

impl Intake {
    fn new(rx: Receiver<Vec<f32>>, recycle: Option<SyncSender<Vec<f32>>>, sample_rate: u32) -> Self {
        Self { rx, recycle, sample_rate, zero_run: 0, stall_timeout: STALL_TIMEOUT }
    }

    /// The next chunk, or None once the stream has closed.
    fn next(&mut self) -> Option<Vec<f32>> {
        loop {
            match self.rx.recv_timeout(self.stall_timeout) {
                Ok(chunk) => {
                    clear_if(AUDIO_ERR_STALLED);
                    self.watch(&chunk);
                    return Some(chunk);
                }
                Err(RecvTimeoutError::Timeout) => report(
                    AUDIO_ERR_STALLED,
                    "the microphone stopped delivering audio (interrupted by a call, or the device went away)",
                ),
                Err(RecvTimeoutError::Disconnected) => return None,
            }
        }
    }

    fn watch(&mut self, chunk: &[f32]) {
        if chunk.iter().all(|&s| s == 0.0) {
            let limit = SILENT_INPUT_S * self.sample_rate as usize;
            self.zero_run += chunk.len();
            if self.zero_run >= limit && self.zero_run - chunk.len() < limit {
                report(AUDIO_WARN_SILENT_INPUT, "the microphone delivers pure silence: is microphone access allowed and the mic not muted?");
            }
        } else if self.zero_run > 0 {
            self.zero_run = 0;
            clear_if(AUDIO_WARN_SILENT_INPUT);
        }
    }

    fn give_back(&self, chunk: Vec<f32>) {
        if let Some(recycle) = &self.recycle {
            let _ = recycle.try_send(chunk);
        }
    }
}

/// Runs until the microphone closes. For the harnesses and tests; the app
/// uses `start_processing_loop_with` to recycle buffers.
pub fn start_processing_loop(rx: Receiver<Vec<f32>>, sample_rate: u32) {
    start_processing_loop_with(rx, sample_rate, None)
}

pub fn start_processing_loop_with(rx: Receiver<Vec<f32>>, sample_rate: u32, recycle: Option<SyncSender<Vec<f32>>>) {
    let intake = Intake::new(rx, recycle, sample_rate);
    if USE_NEURAL.load(Ordering::Relaxed) {
        match StreamingPitchNet::new(sample_rate) {
            Ok(net) => return neural_processing_loop(intake, sample_rate, net),
            Err(e) => report(AUDIO_WARN_NO_PITCH_NET, format!("pitch network unavailable, using DSP evidence: {e}")),
        }
    }
    dsp_processing_loop(intake, sample_rate)
}

fn dsp_processing_loop(mut intake: Intake, sample_rate: u32) {
    let ms_per_sample = 1000.0 / sample_rate as f32;
    let mut analyzer = Analyzer::new(sample_rate);
    let mut follower = Follower::new(Thresholds::DSP);
    let mut audio_vault: Vec<f32> = Vec::new();
    let mut levels = LevelLog::new(sample_rate);
    let mut consumed_samples: u64 = 0; // first sample of the current frame

    // This loop runs when data is received; it ends when the mic stops.
    while let Some(chunk) = intake.next() {
        levels.push(&chunk);
        audio_vault.extend_from_slice(&chunk);
        intake.give_back(chunk);

        while audio_vault.len() >= FFT_SIZE {
            let frame = Frame {
                start_ms: consumed_samples as f32 * ms_per_sample,
                end_ms: (consumed_samples + FFT_SIZE as u64) as f32 * ms_per_sample,
            };
            let building = follower.tracker.is_none();
            if let Some(tracker) = follower.tracker() {
                if building {
                    analyzer.set_templates(templates_for_active_piece());
                }
                // Only run the FFT when some note is expected or still sounding.
                let candidates = tracker.candidates(frame.centre_ms());
                if !candidates.is_empty() {
                    analyzer.analyze(&audio_vault[..FFT_SIZE]);
                    let expected: Vec<f64> = candidates.iter().map(|&i| tracker.pitch_hz(i)).collect();
                    let observations: Vec<(usize, Option<Detection>)> = candidates
                        .iter()
                        .map(|&i| (i, analyzer.evidence(tracker.pitch_hz(i), &expected)))
                        .collect();
                    publish(with_volume(tracker.update(frame, &observations), &levels, tracker.offset_ms()));
                }
            }
            audio_vault.drain(..HOP_SIZE);
            consumed_samples += HOP_SIZE as u64;
        }
    }

    // Stream closed (recording stopped): notes still sounding end here.
    if let Some(tracker) = follower.tracker.as_mut() {
        let end_ms = (consumed_samples + audio_vault.len() as u64) as f32 * ms_per_sample;
        publish(with_volume(tracker.finish(end_ms), &levels, tracker.offset_ms()));
    }
}

/// Like the DSP loop, but the tracker steps through the pitch network's frames
/// (86/s), ~100-300 ms behind live (the network's look-ahead plus its run
/// interval; notes are only reported once they end anyway). For each frame the
/// DSP analyser looks at the audio centred on the same moment, for the
/// measured pitch and the re-attack level.
fn neural_processing_loop(mut intake: Intake, sample_rate: u32, mut net: StreamingPitchNet) {
    let ms_per_sample = 1000.0 / sample_rate as f32;
    let mut analyzer = Analyzer::new(sample_rate);
    let mut follower = Follower::new(Thresholds::NEURAL);
    let mut levels = LevelLog::new(sample_rate);
    // Device audio still needed by the DSP analyser; history[0] is sample `history_start`.
    let mut history: Vec<f32> = Vec::new();
    let mut history_start: usize = 0;
    let mut window = vec![0.0f32; FFT_SIZE];

    let mut step = |frames: Vec<NetFrame>, history: &[f32], history_start: usize, follower: &mut Follower, levels: &LevelLog| {
        for nf in frames {
            let Some(tracker) = follower.tracker() else { continue };
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
            publish(with_volume(tracker.update(frame, &observations), levels, tracker.offset_ms()));
        }
    };

    while let Some(chunk) = intake.next() {
        history.extend_from_slice(&chunk);
        levels.push(&chunk);
        match net.push(&chunk) {
            Ok(frames) => step(frames, &history, history_start, &mut follower, &levels),
            Err(e) => report(AUDIO_ERR_WORKER, format!("pitch network error: {e}")),
        }
        intake.give_back(chunk);
        // The network lags < 1 s; keep 2 s of audio for the DSP windows.
        let keep = 2 * sample_rate as usize;
        if history.len() > keep + sample_rate as usize {
            let drop = history.len() - keep;
            history.drain(..drop);
            history_start += drop;
        }
    }
    match net.finish() {
        Ok(frames) => step(frames, &history, history_start, &mut follower, &levels),
        Err(e) => report(AUDIO_ERR_WORKER, format!("pitch network error at the end of the recording: {e}")),
    }
    if let Some(tracker) = follower.tracker.as_mut() {
        let end_ms = (history_start + history.len()) as f32 * ms_per_sample;
        publish(with_volume(tracker.finish(end_ms), &levels, tracker.offset_ms()));
    }
}

/// The tracker of the piece being played. The piece is read when the tracker
/// is built: the first frame after one is loaded in a scoring phase. Loading
/// another piece (init_session) while recording drops the tracker, notes of
/// the old piece included, and starts following the new one: a piece's clock
/// (see NoteTracker::anchored) belongs to one piece.
struct Follower {
    thresholds: Thresholds,
    tracker: Option<NoteTracker>,
    generation: u64,
}

impl Follower {
    fn new(thresholds: Thresholds) -> Self {
        Self { thresholds, tracker: None, generation: PIECE_GENERATION.load(Ordering::Acquire) }
    }

    fn tracker(&mut self) -> Option<&mut NoteTracker> {
        let current = PIECE_GENERATION.load(Ordering::Acquire);
        if current != self.generation {
            self.generation = current;
            self.tracker = None;
        }
        if self.tracker.is_none() {
            self.tracker = tracker_for_active_piece(self.thresholds);
        }
        self.tracker.as_mut()
    }
}

/// Builds a tracker once a piece is loaded and in a scoring phase.
fn tracker_for_active_piece(thresholds: Thresholds) -> Option<NoteTracker> {
    let guard = lock(&ACTIVE_PIECE);
    let piece = guard.as_ref()?;
    // Phases 0 and 1 are scored against the score; 2 and 3 aren't implemented yet.
    if !matches!(piece.curr_phase, 0 | 1) {
        return None;
    }
    let tracker = NoteTracker::with_thresholds(&piece.notes, thresholds);
    Some(if ANCHOR_CLOCK.load(Ordering::Relaxed) { tracker.anchored() } else { tracker })
}

/// Calibrated note shapes, but only if they were learned on the instrument
/// this piece is for (a piano's harmonics say nothing about a guitar's).
fn templates_for_active_piece() -> Option<NoteTemplates> {
    let instrument = lock(&ACTIVE_PIECE).as_ref()?.instrument.clone()?;
    let templates = lock(&NOTE_TEMPLATES).clone()?;
    (templates.instrument == format!("{instrument:?}")).then_some(templates)
}

/// Sets each note's `volume` from the level log. Notes carry score-clock
/// times, the log is indexed by stream time, so the tracker's clock offset is
/// added back: with the clock anchored to the first note, a note scored at
/// 0 ms may have been played 5 s into the recording.
fn with_volume(mut notes: Vec<Notes>, levels: &LevelLog, offset_ms: f32) -> Vec<Notes> {
    for note in &mut notes {
        if let (Some(start), Some(end)) = (note.start_time_ms, note.end_time_ms) {
            note.volume = levels.peak_volume(start + offset_ms, end + offset_ms);
        }
    }
    notes
}

/// Buffers finished notes and streams them to Dart when it is listening.
/// With no listener (tests, CLI harness, or Dart has stopped listening) they
/// stay in USER_DATA, where get_user_data can still hand them over.
fn publish(notes: Vec<Notes>) {
    if notes.is_empty() {
        return;
    }
    let mut user_data = lock(&USER_DATA);
    let buffered = user_data.get_or_insert_with(Vec::new);
    buffered.extend(notes);
    let sink = NOTES_SINK.read().unwrap_or_else(|e| e.into_inner());
    if let Some(sink) = sink.as_ref()
        && sink.add(buffered.clone()).is_ok()
    {
        buffered.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dsp::cents;
    use crate::models::{PieceData, TimingSpecs};
    use std::f32::consts::PI;

    // Tests that drive start_processing_loop share the ACTIVE_PIECE, USER_DATA
    // and status globals, so they must not run at the same time.
    use super::TEST_LOCK as LOOP_TEST_LOCK;

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
                volume: None,
            }],
        }
    }

    /// `silence_ms` of silence, `tone_ms` of A4 with harmonics, then `tail_ms`
    /// of silence, sent in mic-sized chunks. The score clock is the stream's
    /// (the note is scored where it is played). Returns this note's records.
    fn run_a4(rate: u32, note_id: u64, silence_ms: f32, tone_ms: f32, tail_ms: f32) -> Vec<Notes> {
        run_a4_scored(rate, note_id, silence_ms, tone_ms, tail_ms, silence_ms, false)
    }

    /// As `run_a4`, with the note scored at `score_start_ms`. `anchor` starts
    /// the score's clock at the first note, as the app does.
    fn run_a4_scored(rate: u32, note_id: u64, silence_ms: f32, tone_ms: f32, tail_ms: f32, score_start_ms: f32, anchor: bool) -> Vec<Notes> {
        let _serial = LOOP_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        ANCHOR_CLOCK.store(anchor, Ordering::Relaxed);
        *ACTIVE_PIECE.lock().unwrap() = Some(a4_piece(note_id, score_start_ms, score_start_ms + tone_ms));
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
        ANCHOR_CLOCK.store(true, Ordering::Relaxed);

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

    /// As `run_a4`, with the tone scaled by `gain` (each test needs its own
    /// `note_id`: USER_DATA is shared). With `anchor` the score's
    /// clock starts at the first note, so the note is scored at 0 although it
    /// is played at `silence_ms` of stream time, as in the app.
    fn run_tone(note_id: u64, gain: f32, silence_ms: f32, tone_ms: f32, tail_ms: f32, anchor: bool) -> Vec<Notes> {
        let rate = 44100;
        let _serial = LOOP_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        ANCHOR_CLOCK.store(anchor, Ordering::Relaxed);
        let score_start = if anchor { 0.0 } else { silence_ms };
        *ACTIVE_PIECE.lock().unwrap() = Some(a4_piece(note_id, score_start, score_start + tone_ms));
        let samples = |ms: f32| (ms / 1000.0 * rate as f32) as usize;
        let mut audio = vec![0.0f32; samples(silence_ms)];
        audio.extend((0..samples(tone_ms)).map(|i| {
            let t = i as f32 / rate as f32;
            gain * (1..=6).map(|k| 0.3 / k as f32 * (2.0 * PI * 440.0 * k as f32 * t).sin()).sum::<f32>()
        }));
        audio.extend(vec![0.0f32; samples(tail_ms)]);

        let (tx, rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || start_processing_loop(rx, rate));
        for chunk in audio.chunks(512) {
            tx.send(chunk.to_vec()).unwrap();
        }
        drop(tx);
        worker.join().unwrap();
        *ACTIVE_PIECE.lock().unwrap() = None;
        ANCHOR_CLOCK.store(true, Ordering::Relaxed);

        let user_data = USER_DATA.lock().unwrap();
        user_data.iter().flatten().filter(|n| n.note_id == note_id).cloned().collect()
    }

    // That tone (six harmonics at 0.3/k) is -8.72 dBFS RMS: volume (60 - 8.72) / 60.
    const FULL_TONE_VOLUME: f32 = 0.8546;

    #[test]
    fn test_a_played_note_carries_the_volume_it_was_played_at() {
        let notes = run_tone(9501, 1.0, 300.0, 500.0, 500.0, false);
        assert_eq!(notes.len(), 1, "{notes:?}");
        assert_close("volume", notes[0].volume, FULL_TONE_VOLUME, 0.03);
    }

    #[test]
    fn test_a_quieter_note_gets_a_proportionally_lower_volume() {
        // Gain 0.25 is 12.04 dB down: 12.04 / 60 = 0.2007 lower on the 0..1 scale.
        let notes = run_tone(9502, 0.25, 300.0, 500.0, 500.0, false);
        assert_eq!(notes.len(), 1, "{notes:?}");
        assert_close("volume", notes[0].volume, FULL_TONE_VOLUME - 0.2007, 0.03);
    }

    #[test]
    fn test_volume_is_read_from_the_notes_own_audio_when_the_score_clock_is_anchored() {
        // Anchored, the note is reported at ~0 ms of score time but was played
        // 1.2 s into the stream. Looking at the first 500 ms would find silence.
        let notes = run_tone(9503, 1.0, 1200.0, 500.0, 500.0, true);
        assert_eq!(notes.len(), 1, "{notes:?}");
        assert!(notes[0].start_time_ms.unwrap() < 100.0, "score time should start near 0: {notes:?}");
        assert_close("volume", notes[0].volume, FULL_TONE_VOLUME, 0.03);
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
    fn test_clock_starts_at_the_first_note_however_long_the_mic_was_open_before() {
        // The app opens the mic a beat before the downbeat. The note is scored
        // at 0 ms; it is played 1.2 s into the stream (at 44.1 and 48 kHz).
        for rate in [44100, 48000] {
            let notes = run_a4_scored(rate, 9400 + rate as u64 / 1000, 1200.0, 500.0, 500.0, 0.0, true);
            assert_eq!(notes.len(), 1, "{rate} Hz: {notes:?}");
            assert_close("start", notes[0].start_time_ms, 0.0, 0.5);
            assert_close("end", notes[0].end_time_ms, 500.0, TIMING_TOLERANCE_MS);
        }
    }

    #[test]
    fn test_without_the_anchor_the_same_recording_is_off_by_the_lead() {
        // What anchoring is for: the note scored at 0 ms, played at 1.2 s.
        let notes = run_a4_scored(44100, 9402, 1200.0, 500.0, 500.0, 0.0, false);
        assert!(notes.is_empty(), "outside its window, so not heard at all: {notes:?}");
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

#[cfg(test)]
pub(crate) static TEST_LOCK: Mutex<()> = Mutex::new(());

#[cfg(test)]
mod capture_tests {
    use super::*;

    fn sink(queue: usize, pool: usize, channels: usize) -> (ChunkSink, Receiver<Vec<f32>>, SyncSender<Vec<f32>>) {
        let (tx, rx) = sync_channel(queue);
        let (recycle, pool_rx) = sync_channel(pool);
        for _ in 0..pool {
            recycle.try_send(Vec::with_capacity(CHUNK_CAPACITY)).unwrap();
        }
        (ChunkSink { tx, pool: pool_rx, channels }, rx, recycle)
    }

    #[test]
    fn test_integer_formats_convert_to_the_same_range_as_f32() {
        let mut out = Vec::new();
        downmix_into(&mut out, &[i16::MAX, i16::MIN, 0], 1);
        assert!((out[0] - 1.0).abs() < 1e-3 && (out[1] + 1.0).abs() < 1e-3 && out[2] == 0.0, "{out:?}");
        // Unsigned formats are centred on half scale: silence is 32768, not 0.
        out.clear();
        downmix_into(&mut out, &[u16::MAX, 0u16, 32768], 1);
        assert!(out[0] > 0.99 && out[1] < -0.99 && out[2].abs() < 1e-3, "{out:?}");
        out.clear();
        downmix_into(&mut out, &[0.5f64, -0.25], 1);
        assert_eq!(out, vec![0.5, -0.25]);
        out.clear();
        downmix_into(&mut out, &[i32::MAX / 2, 0], 1);
        assert!((out[0] - 0.5).abs() < 1e-3, "{out:?}");
    }

    #[test]
    fn test_stereo_and_multichannel_i16_are_averaged() {
        let mut out = Vec::new();
        downmix_into(&mut out, &[16384i16, -16384, 16384, 16384], 2);
        assert!(out[0].abs() < 1e-3 && (out[1] - 0.5).abs() < 1e-3, "{out:?}");
        // Four inputs of an audio interface, only the first has a signal.
        out.clear();
        downmix_into(&mut out, &[1.0f32, 0.0, 0.0, 0.0], 4);
        assert_eq!(out, vec![0.25]);
        // A zero channel count must not panic (chunks_exact(0) would).
        out.clear();
        downmix_into(&mut out, &[0.1f32, 0.2], 0);
        assert_eq!(out, vec![0.1, 0.2]);
    }

    #[test]
    fn test_callback_reuses_recycled_buffers_instead_of_allocating() {
        let (mut sink, rx, recycle) = sink(8, 1, 2);
        let data = vec![0.5f32; 1024];
        sink.push(&data);
        let chunk = rx.try_recv().unwrap();
        let first = chunk.as_ptr();
        assert_eq!(chunk.len(), 512, "mono: 1024 interleaved stereo samples");
        recycle.try_send(chunk).unwrap();
        sink.push(&data);
        let again = rx.try_recv().unwrap();
        assert_eq!(again.as_ptr(), first, "the same buffer came round again");
        assert_eq!(again.len(), 512, "and it was emptied first");
    }

    #[test]
    fn test_callback_costs_microseconds() {
        // A callback comes every 10-20 ms (512-1024 frames at 44.1-48 kHz) and
        // must be done long before the next one.
        let (mut sink, rx, recycle) = sink(QUEUE_CHUNKS, POOL_CHUNKS, 2);
        let data = vec![0.1f32; 2 * 1024];
        let n = 20_000;
        let started = std::time::Instant::now();
        for _ in 0..n {
            sink.push(&data);
            if let Ok(chunk) = rx.try_recv() {
                let _ = recycle.try_send(chunk);
            }
        }
        let per_call = started.elapsed() / n;
        println!("capture callback: {per_call:?} per 1024-frame stereo buffer");
        assert!(per_call < Duration::from_micros(500), "{per_call:?}");
    }

    #[test]
    fn test_a_stuck_consumer_makes_the_callback_drop_audio_not_block_or_grow() {
        let _serial = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        clear_status();
        let (mut sink, rx, _recycle) = sink(4, 4, 1);
        let started = std::time::Instant::now();
        for _ in 0..10_000 {
            sink.push(&[0.1f32; 512]); // nobody receives
        }
        assert!(started.elapsed() < Duration::from_secs(1), "the callback must never wait for the consumer");
        assert_eq!(rx.try_iter().count(), 4, "the queue holds its capacity and no more");
        assert_eq!(status(), AUDIO_ERR_OVERRUN);
        assert!(!status_message().is_empty());
        clear_status();
    }

    #[test]
    fn test_a_warning_never_hides_an_error() {
        let _serial = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        clear_status();
        report(AUDIO_WARN_SILENT_INPUT, "quiet");
        assert_eq!(status(), AUDIO_WARN_SILENT_INPUT);
        report(AUDIO_ERR_STREAM, "device gone");
        report(AUDIO_WARN_NO_PITCH_NET, "no net");
        assert_eq!((status(), status_message().as_str()), (AUDIO_ERR_STREAM, "device gone"));
        clear_status();
        assert_eq!((status(), status_message().as_str()), (AUDIO_OK, ""));
    }

    fn intake_with(chunks: Vec<Vec<f32>>, rate: u32) -> Intake {
        let (tx, rx) = std::sync::mpsc::channel();
        for c in chunks {
            tx.send(c).unwrap();
        }
        Intake::new(rx, None, rate)
    }

    #[test]
    fn test_a_microphone_feeding_pure_silence_is_reported_and_forgiven_when_sound_arrives() {
        let _serial = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        clear_status();
        // 1.125 s of exact zeros at 8 kHz, as iOS feeds an app without microphone permission.
        let mut intake = intake_with(vec![vec![0.0; 3000], vec![0.0; 3000], vec![0.0; 3000], vec![0.01; 100]], 8000);
        for _ in 0..2 {
            intake.next().unwrap();
        }
        assert_eq!(status(), AUDIO_OK, "0.75 s of silence is normal: a pause before playing");
        intake.next().unwrap();
        assert_eq!(status(), AUDIO_WARN_SILENT_INPUT);
        intake.next().unwrap();
        assert_eq!(status(), AUDIO_OK, "real signal clears the warning");
    }

    #[test]
    fn test_a_stalled_stream_is_reported_and_resumes() {
        let _serial = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        clear_status();
        let (tx, rx) = std::sync::mpsc::channel();
        let mut intake = Intake::new(rx, None, 8000);
        intake.stall_timeout = Duration::from_millis(30);
        let feeder = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(200));
            let during_the_stall = status();
            tx.send(vec![0.1; 100]).unwrap();
            during_the_stall // tx dropped: the stream closed
        });
        assert!(intake.next().is_some(), "the chunk arrives after the stall");
        assert_eq!(status(), AUDIO_OK, "and the stall is forgiven");
        assert!(intake.next().is_none(), "a closed stream ends the loop");
        assert_eq!(feeder.join().unwrap(), AUDIO_ERR_STALLED);
        clear_status();
    }
}

