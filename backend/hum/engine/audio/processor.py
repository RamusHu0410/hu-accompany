"""Reads a hummed WAV and finds its notes.

    WAV file ─ inspect_wav ─ load (mono, 22050 Hz) ─ filter_audio ─ pYIN pitch + loudness per frame
             ─ notes.segment_notes ─ melody (MIDI note, start and duration in seconds) + tempo + key

``filter_audio`` is the one cleanup chain every analysis runs through: DC offset removed,
rumble and mains hum (50/60 Hz) filtered out, hiss above the voice's range filtered out, steady
background noise subtracted, then the level normalized. The accompanist engine wants beats, not
seconds; ``hum.engine.audio.handoff`` does that conversion.
"""

import dataclasses
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import librosa
import librosa.beat
import librosa.feature
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from .intake import AudioInputError, inspect_wav
from .notes import DEFAULT_SETTINGS, NoteSettings, estimate_tempo_from_onsets, estimate_tuning, noise_gate, segment_notes, sounding_runs

logger = logging.getLogger(__name__)

# --- the cleanup chain (filter_audio) ---------------------------------------------------------
# The high-pass takes rumble, handling noise and mains hum: run forwards and backwards it is
# ~-24 dB at 50 Hz and ~-13 dB at 60 Hz, ~-2 dB at E2 (82 Hz). Narrow 50/60 Hz notches were
# tried and dropped: their long ring, run backwards by filtfilt, put a ghost ~60 Hz "note" in
# the silence before the first real one.
HIGHPASS_HZ = 70.0
LOWPASS_HZ = 6000.0  # hiss; a whistle's fundamental stays under ~2.5 kHz
NORMALIZED_PEAK = 0.9

# --- pitch tracking ---------------------------------------------------------------------------
PITCH_FMIN_HZ = 65.0  # C2: a low male hum
PITCH_FMAX_HZ = 2000.0  # ~B6: whistling and high sopranos (was 800 Hz, which misread whistles)

# --- warnings about the recording itself ------------------------------------------------------
CLIPPED_LEVEL = 0.999  # samples at or above this (full scale 1.0) are clipped
CLIPPED_SHARE = 0.001  # more than this share of clipped samples earns a warning
QUIET_PEAK = 0.03  # a recording that never gets louder than ~-30 dBFS is too quiet
UNPITCHED_SHARE = 0.5  # more than this share of the sound unpitched: not a clear single tune
MIN_OUTPUT_NOTE_SECONDS = 0.3  # finalized notes shorter than 300 ms are transient artifacts

SILENT_RMS = 0.001


def console_print(message: str, level: str = "INFO"):
    """Print to console with timestamp and flush immediately (debug mode only)."""
    timestamp = time.strftime("%H:%M:%S")
    prefix = {
        "INFO": "ℹ️",
        "DEBUG": "🔍",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "✅",
        "PROCESS": "⚙️",
    }.get(level, "📝")
    print(f"[{timestamp}] {prefix} {message}", flush=True)


class AudioProcessor:
    """Loads, cleans and analyses a WAV recording.

    Uses librosa for analysis (pitch, tempo, spectral features), soundfile for file I/O, and
    scipy.signal for the filters in ``filter_audio``.
    """

    def __init__(
        self,
        target_sr: int = 22050,
        hop_length: int = 512,
        frame_length: int = 2048,
        debug: bool = False,
    ):
        """
        Args:
            target_sr: Sample rate every recording is resampled to before analysis
            hop_length: Samples between frames for the volume/spectral features
            frame_length: FFT window for the volume/spectral features
            debug: Print what each step is doing
        """
        self.target_sr = target_sr
        self.hop_length = hop_length
        self.frame_length = frame_length
        self.debug = debug

    def _debug_print(self, message: str, level: str = "DEBUG"):
        if self.debug:
            console_print(message, level)
            logger.debug(message)

    # ------------------------------------------------------------------ loading and cleaning

    def load_wav(self, filepath: str) -> Tuple[np.ndarray, int]:
        """The recording as mono float32 at ``target_sr``, whatever its channels, rate or bit depth.

        Raises AudioInputError if the file is missing, unreadable, empty, too short or too long.
        """
        self._debug_print(f"Loading WAV file: {filepath}", "PROCESS")
        inspect_wav(filepath)
        try:
            audio, sr = librosa.load(filepath, sr=self.target_sr, mono=True)
        except Exception as exc:  # a header that parses but data that doesn't
            raise AudioInputError("That file isn't a readable WAV recording.") from exc
        audio = np.nan_to_num(audio.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        if audio.size == 0:
            raise AudioInputError("The recording is empty.")
        self._debug_print(f"Loaded {len(audio)} samples at {sr} Hz ({len(audio) / sr:.2f}s)", "SUCCESS")
        return audio, sr

    def filter_audio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """The cleanup chain every analysis runs on. Same length as the input, so times still
        match the original recording.

        1. DC offset removed (a cheap mic's constant bias skews every loudness measure).
        2. High-pass at HIGHPASS_HZ for rumble and mains hum.
        3. Low-pass at LOWPASS_HZ for hiss.
        4. Steady background noise subtracted (``reduce_noise``).
        5. Peak normalized to NORMALIZED_PEAK, so a quiet recording reads like a loud one.
        """
        cleaned = np.asarray(audio, dtype=np.float64)
        if cleaned.size == 0:
            return cleaned.astype(np.float32)
        cleaned = cleaned - np.mean(cleaned)

        nyquist = sr / 2.0
        sections = [butter(4, HIGHPASS_HZ, btype="highpass", fs=sr, output="sos")]
        if LOWPASS_HZ < nyquist * 0.95:
            sections.append(butter(4, LOWPASS_HZ, btype="lowpass", fs=sr, output="sos"))
        sos = np.vstack(sections)
        if cleaned.size > 3 * (2 * len(sos) + 1):  # sosfiltfilt needs a little signal to pad with
            cleaned = sosfiltfilt(sos, cleaned)

        cleaned = self.reduce_noise(cleaned.astype(np.float32), sr)

        peak = float(np.max(np.abs(cleaned)))
        if peak > 0:
            cleaned = cleaned * (NORMALIZED_PEAK / peak)
        self._debug_print(f"Filtered audio (peak before normalizing {peak:.4f})", "SUCCESS")
        return cleaned.astype(np.float32)

    def clean_audio(self, audio: np.ndarray, sr: int, trim: bool = True, top_db: float = 30.0) -> np.ndarray:
        """``filter_audio``, then (by default) the silence at either end trimmed off. Trimming
        shifts every time, so the analysis itself never trims; this is for making a listenable copy."""
        cleaned = self.filter_audio(audio, sr)
        if trim and cleaned.size:
            cleaned, _ = librosa.effects.trim(cleaned, top_db=top_db)
        return cleaned.astype(np.float32)

    def reduce_noise(
        self,
        audio: np.ndarray,
        sr: int,
        n_fft: int = 2048,
        oversubtract: float = 1.6,
        spectral_floor: float = 0.05,
        quiet_margin_db: float = 6.0,
        min_contrast_db: float = 15.0,
    ) -> np.ndarray:
        """Subtract steady background noise (room hiss, fan, mic hum) by spectral subtraction.

        The noise profile is learned only from frames that are clearly quiet: within
        ``quiet_margin_db`` of the recording's quietest tenth *and* at least ``min_contrast_db``
        under its loud parts. (It used to take "30 dB under the peak", which a phone recording
        with its noise floor at -25 dB never reaches, so noisy recordings were never cleaned.)
        A note held for the whole clip has no quiet frames, so nothing is learned and the audio
        is returned unchanged; guessing a profile there would subtract the note itself.

        Each frame is cleaned on its own (no smoothing across time), so the gaps between notes
        stay exactly where they were.
        """
        if audio.size == 0 or not np.any(audio):
            return audio.astype(np.float32)

        hop_length = n_fft // 4
        stft = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
        magnitude, phase = np.abs(stft), np.angle(stft)

        frame_db = 20 * np.log10(np.maximum(np.sqrt(np.mean(magnitude**2, axis=0)), 1e-10))
        quiet_limit = min(
            np.percentile(frame_db, 10) + quiet_margin_db,
            np.percentile(frame_db, 95) - min_contrast_db,
        )
        noise_only_frames = magnitude[:, frame_db <= quiet_limit]
        if noise_only_frames.shape[1] < 2:
            self._debug_print("No clearly quiet frames to learn the noise from; skipping denoise", "WARNING")
            return audio.astype(np.float32)

        noise_floor = np.mean(noise_only_frames, axis=1, keepdims=True)
        cleaned_magnitude = np.maximum(magnitude - oversubtract * noise_floor, spectral_floor * magnitude)
        cleaned = librosa.istft(cleaned_magnitude * np.exp(1j * phase), hop_length=hop_length, length=len(audio))
        self._debug_print(
            f"Noise reduction: mean magnitude {np.mean(magnitude):.4f} -> {np.mean(cleaned_magnitude):.4f}",
            "SUCCESS",
        )
        return cleaned.astype(np.float32)

    def get_audio_info(self, filepath: str) -> Dict[str, Any]:
        """duration, sample_rate, channels, frames, format and subtype, from the file header."""
        info = sf.info(filepath)
        return {
            "duration": info.duration,
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "frames": info.frames,
            "format": info.format,
            "subtype": info.subtype,
        }

    # ------------------------------------------------------------------ analysis

    def detect_sound_segments(
        self, audio: np.ndarray, sr: int, top_db: float = 30, min_duration: float = 0.1
    ) -> List[Dict[str, float]]:
        """Stretches where there's sound at all (for the silence statistics). Notes are found from
        the pitch track instead (see ``notes.segment_notes``): loudness alone can't tell a legato
        C-D-E apart from one long note."""
        intervals = librosa.effects.split(audio, top_db=top_db, frame_length=self.frame_length, hop_length=self.hop_length)
        segments = []
        for start_sample, end_sample in intervals:  # librosa returns sample indices
            start, end = start_sample / sr, end_sample / sr
            if end - start >= min_duration:
                segments.append({"start": float(start), "end": float(end), "duration": float(end - start)})
        self._debug_print(f"Sound segments: {len(segments)}")
        return segments

    def extract_pitch(
        self, audio: np.ndarray, sr: int, fmin: float = PITCH_FMIN_HZ, fmax: float = PITCH_FMAX_HZ
    ) -> Dict[str, Any]:
        """Fundamental frequency per frame (pYIN), with each frame's loudness alongside.

        The window is ~50 ms rather than self.frame_length (~93 ms): a hummed note wavers
        (vibrato, 5-7 Hz), and a window spanning much of a vibrato cycle pools a moving pitch
        into one biased estimate (a +/-100 Hz wobble around 440 Hz read as ~465 Hz with the wider
        window, ~447 Hz with this one). It's floored at the two periods of fmin pYIN needs.
        """
        fmax = min(fmax, sr / 2 * 0.9)
        frame_length = max(int(np.ceil(2 * sr / fmin)), min(self.frame_length, int(sr * 0.05)))
        hop_length = max(1, frame_length // 4)
        self._debug_print(f"pYIN {fmin:.0f}-{fmax:.0f} Hz, frame {frame_length}, hop {hop_length}", "PROCESS")

        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio, fmin=fmin, fmax=fmax, sr=sr, frame_length=frame_length, hop_length=hop_length
        )
        # Loudness on a shorter window than the pitch (~25 ms), on the same frame grid, so the
        # brief dip of a re-sung note ("da-da") isn't averaged away.
        rms = librosa.feature.rms(y=audio, frame_length=2 * hop_length, hop_length=hop_length)[0]
        frames = min(len(f0), len(rms))
        f0, voiced_flag, voiced_probs, rms = f0[:frames], voiced_flag[:frames], voiced_probs[:frames], rms[:frames]
        times = librosa.frames_to_time(np.arange(frames), sr=sr, hop_length=hop_length)
        voiced_f0 = f0[voiced_flag]
        has_voice = voiced_f0.size > 0

        return {
            "frequencies": f0.tolist(),
            "times": times.tolist(),
            # tolist() can keep NumPy bool scalars on some versions; JSON needs plain bools
            "voiced_flag": [bool(flag) for flag in voiced_flag],
            "voiced_probabilities": voiced_probs.tolist(),
            "rms_db": (20 * np.log10(np.maximum(rms, 1e-10))).tolist(),
            "mean_hz": float(np.nanmean(voiced_f0)) if has_voice else 0.0,
            "median_hz": float(np.nanmedian(voiced_f0)) if has_voice else 0.0,
            "min_hz": float(np.nanmin(voiced_f0)) if has_voice else 0.0,
            "max_hz": float(np.nanmax(voiced_f0)) if has_voice else 0.0,
            "voiced_duration": float(np.sum(voiced_flag) * hop_length / sr),
            "total_frames": int(frames),
            "voiced_frames": int(np.sum(voiced_flag)),
        }

    def extract_volume_envelope(self, audio: np.ndarray, sr: int) -> Dict[str, Any]:
        """RMS loudness over time."""
        rms = librosa.feature.rms(y=audio, frame_length=self.frame_length, hop_length=self.hop_length)[0]
        rms_db = librosa.amplitude_to_db(rms, ref=np.max)
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=self.hop_length)
        return {
            "rms_values": rms.tolist(),
            "rms_db": rms_db.tolist(),
            "times": times.tolist(),
            "mean_rms": float(np.mean(rms)),
            "max_rms": float(np.max(rms)),
            "mean_db": float(np.mean(rms_db)),
            "max_db": float(np.max(rms_db)),
            "dynamic_range_db": float(np.max(rms_db) - np.min(rms_db)),
        }

    def extract_spectral_features(self, audio: np.ndarray, sr: int) -> Dict[str, Any]:
        """Spectral centroid, rolloff, bandwidth and zero-crossing rate."""
        centroid = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=self.hop_length)[0]
        rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr, hop_length=self.hop_length)[0]
        bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sr, hop_length=self.hop_length)[0]
        zcr = librosa.feature.zero_crossing_rate(audio, frame_length=self.frame_length, hop_length=self.hop_length)[0]
        times = librosa.frames_to_time(np.arange(len(centroid)), sr=sr, hop_length=self.hop_length)

        def summary(values, with_times=False):
            out = {"values": values.tolist(), "mean": float(np.mean(values)), "std": float(np.std(values))}
            return {**out, "times": times.tolist()} if with_times else out

        return {
            "spectral_centroid": summary(centroid, with_times=True),
            "spectral_rolloff": summary(rolloff),
            "spectral_bandwidth": summary(bandwidth),
            "zero_crossing_rate": summary(zcr),
        }

    def process_audio(
        self,
        filepath: str,
        detect_segments: bool = True,
        extract_pitch: bool = True,
        extract_volume: bool = True,
        extract_spectral: bool = True,
        clean: bool = True,
    ) -> Dict[str, Any]:
        """Load, clean and analyse a WAV file.

        Args:
            filepath: Path to the WAV file
            detect_segments: Find the stretches with sound (silence statistics)
            extract_pitch: Track pitch and loudness per frame (needed for notes)
            extract_volume: RMS envelope
            extract_spectral: Spectral features
            clean: Run ``filter_audio`` first, so every feature reads the cleaned signal

        Raises:
            AudioInputError: the file can't be used (see ``intake.inspect_wav``)
        """
        started = time.time()
        raw, sr = self.load_wav(filepath)
        warnings = _input_warnings(raw)
        audio = self.filter_audio(raw, sr) if clean else raw
        self.audio, self.sr = audio, sr

        duration = len(audio) / sr
        raw_rms = float(np.sqrt(np.mean(raw**2)))
        results: Dict[str, Any] = {
            "file": {
                "path": filepath,
                "duration": float(duration),
                "sample_rate": sr,
                "num_samples": len(audio),
                # measured on the recording as it arrived: normalizing would make silence look loud
                "rms_energy": raw_rms,
                "max_amplitude": float(np.max(np.abs(raw))),
                "is_silent": raw_rms < SILENT_RMS,
                "info": self.get_audio_info(filepath),
                "warnings": warnings,
            },
            "segments": [],
            "pitch": {},
            "volume": {},
            "spectral": {},
            "processing_time": 0.0,
        }

        if detect_segments:
            segments = self.detect_sound_segments(audio, sr)
            sound = sum(s["duration"] for s in segments)
            results["segments"] = segments
            results["file"]["total_sound_duration"] = float(sound)
            results["file"]["silence_ratio"] = float(1.0 - sound / duration) if duration > 0 else 1.0
            results["file"]["num_segments"] = len(segments)
        if extract_pitch:
            results["pitch"] = self.extract_pitch(audio, sr)
        if extract_volume:
            results["volume"] = self.extract_volume_envelope(audio, sr)
        if extract_spectral:
            results["spectral"] = self.extract_spectral_features(audio, sr)

        results["processing_time"] = round(time.time() - started, 3)
        logger.info("Processed audio: %s (%.2fs, %dHz, RMS %.4f)", filepath, duration, sr, raw_rms)
        return results


# =============================================================================
# From analysis to notes
# =============================================================================

_PITCH_CLASS_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# Krumhansl-Kessler key profiles
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _best_key(profile: np.ndarray) -> tuple[str, str]:
    """Krumhansl-Schmuckler: the key whose profile correlates best with this pitch-class profile."""
    if not np.any(profile) or np.allclose(profile, profile[0]):
        return "C", "major"
    candidates = [
        (float(np.corrcoef(profile, np.roll(template, tonic))[0, 1]), tonic, mode)
        for template, mode in ((_MAJOR_PROFILE, "major"), (_MINOR_PROFILE, "minor"))
        for tonic in range(12)
    ]
    _, tonic, mode = max(candidates)
    return _PITCH_CLASS_NAMES[tonic], mode


def _estimate_key_and_mode(audio: np.ndarray, sr: int) -> tuple[str, str]:
    """Key and mode from the audio's chroma. Only a fallback: the notes are a cleaner signal."""
    if audio.size == 0 or np.allclose(audio, 0):
        return "C", "major"
    return _best_key(np.mean(librosa.feature.chroma_cqt(y=audio, sr=sr), axis=1))


def _key_from_melody(melody: List[Dict[str, float]]) -> tuple[str, str]:
    """Key and mode from the notes, each weighted by how long it's held."""
    profile = np.zeros(12)
    for note in melody:
        profile[int(round(note["hz"])) % 12] += note["duration"]
    return _best_key(profile)


def _estimate_tempo(audio: np.ndarray, sr: int) -> float:
    """librosa's beat-tracker tempo in BPM, or 0.0. Needs percussive attacks, so it rarely works
    on a hum; ``estimate_tempo_from_onsets`` is tried first."""
    if audio.size == 0 or np.allclose(audio, 0):
        return 0.0
    try:
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
        tempo_arr = np.asarray(tempo).reshape(-1)
        return round(float(tempo_arr[0]), 2) if tempo_arr.size else 0.0
    except Exception:
        return 0.0


def _pitch_track(pitch: Dict[str, Any]):
    """times, fractional MIDI, sounding-frame mask and loudness (or None) from ``extract_pitch``."""
    times = np.asarray(pitch.get("times", []), dtype=float)
    hz = np.asarray(pitch.get("frequencies", []), dtype=float)
    voiced = np.asarray(pitch.get("voiced_flag", []), dtype=bool)
    frames = min(len(times), len(hz), len(voiced))
    times, hz, voiced = times[:frames], hz[:frames], voiced[:frames]
    rms_db = pitch.get("rms_db")
    rms_db = np.asarray(rms_db, dtype=float)[:frames] if rms_db is not None and len(rms_db) >= frames else None

    midi = np.full(frames, np.nan)
    pitched = np.isfinite(hz) & (hz > 0)
    midi[pitched] = librosa.hz_to_midi(hz[pitched])
    active = voiced & pitched
    return times, midi, active, rms_db


MAX_CONTOUR_POINTS = 900  # the graph is ~640 px wide; more points than this only cost bytes


def pitch_contour(
    pitch: Dict[str, Any],
    tuning: float = 0.0,
    settings: NoteSettings = DEFAULT_SETTINGS,
) -> Dict[str, Any]:
    """The frame-by-frame pitch track, compact enough to send to the browser.

    The notes graph draws the hum as it was actually sung -- every scoop, slide and wobble --
    rather than as the rectangles ``segment_notes`` rounds it into. Each run of sounding frames
    becomes one segment, so a phrase is one smooth curve and silences break the line instead of
    being drawn through::

        {"step": 0.012, "segments": [{"start": 0.23, "midi": [60.1, ...], "level": [0.4, ...]}]}

    ``midi`` is tuning-corrected like the notes, and ``level`` is loudness rescaled to 0-1
    between the noise gate and the loudest frame, which is what the drawing uses for the
    thickness and opacity of the line.
    """
    if not isinstance(pitch, dict):
        return {"step": 0.0, "segments": []}
    times, midi, active, rms_db = _pitch_track(pitch)
    if times.size < 2:
        return {"step": 0.0, "segments": []}

    if rms_db is not None and rms_db.size:
        gate = noise_gate(rms_db, settings)
        active = active & (rms_db >= gate)
        top = float(np.max(rms_db[np.isfinite(rms_db)])) if np.isfinite(rms_db).any() else gate
        span = max(top - gate, 1e-6)
        level = np.clip((rms_db - gate) / span, 0.0, 1.0)
    else:
        level = np.ones_like(times)

    step = float(np.median(np.diff(times)))
    keep = max(1, int(np.ceil(int(np.sum(active)) / MAX_CONTOUR_POINTS)))  # thin evenly if it's long
    segments = []
    for start, stop in sounding_runs(active):
        index = np.arange(start, stop, keep)
        if index.size < 2:
            continue
        segments.append(
            {
                "start": round(float(times[index[0]]), 3),
                "midi": [round(float(m), 2) for m in midi[index] - tuning],
                "level": [round(float(l), 3) for l in level[index]],
            }
        )
    return {"step": round(step * keep, 4), "segments": segments}


def _notes_from_pitch(pitch: Dict[str, Any], settings: NoteSettings = DEFAULT_SETTINGS):
    """(notes, tuning offset in semitones, share of the sound that was unpitched)."""
    if not isinstance(pitch, dict):
        return [], 0.0, 0.0
    times, midi, active, rms_db = _pitch_track(pitch)
    unpitched_share = 0.0
    if rms_db is not None and rms_db.size:
        loud = rms_db >= noise_gate(rms_db, settings)
        unpitched_share = float(np.mean(~active[loud])) if loud.any() else 0.0
        active = active & loud
    notes = segment_notes(times, midi, active, rms_db, settings)
    # Keep segmentation sensitive enough to separate nearby notes, then discard transient
    # finalized notes at the output boundary using their unrounded real-time duration.
    notes = [note for note in notes if note["duration"] + 1e-9 >= MIN_OUTPUT_NOTE_SECONDS]
    tuning = estimate_tuning(notes, settings)
    for note in notes:
        note["midi"] -= tuning
    return notes, tuning, unpitched_share


def _build_melody(analysis: Dict[str, Any], settings: NoteSettings = DEFAULT_SETTINGS) -> List[Dict[str, float]]:
    """The notes of a ``process_audio`` result as {hz, start, duration}, times in seconds.

    ``hz`` holds a (fractional, tuning-corrected) MIDI note number, e.g. 60.0 for middle C: the
    field name is the accompaniment API's historical one. See ``hum.engine.audio.handoff`` for beats.
    """
    notes, _, _ = _notes_from_pitch(analysis.get("pitch", {}), settings)
    return [{"hz": round(n["midi"], 2), "start": round(n["start"], 3), "duration": round(n["duration"], 3)} for n in notes]


# Public name for routes; tests use ``_build_melody``.
build_melody = _build_melody


def _input_warnings(audio: np.ndarray) -> List[str]:
    """Problems with the recording itself that may cost notes, in words for the user."""
    warnings = []
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if audio.size and np.mean(np.abs(audio) >= CLIPPED_LEVEL) > CLIPPED_SHARE:
        warnings.append("The recording is clipping (too loud or too close to the mic), so some notes may be misheard.")
    elif 0 < peak < QUIET_PEAK:
        warnings.append("The recording is very quiet. Hum a little closer to the mic.")
    return warnings


def analyze_audio_file(
    filepath: str,
    target_sr: int = 22050,
    settings: NoteSettings = DEFAULT_SETTINGS,
    keep_analysis: bool = False,
    debug: bool = False,
) -> Dict[str, Any]:
    """The hum's notes, tempo and key, JSON-ready::

        {
            "melody": [{"hz": 60.0, "start": 0.0, "duration": 0.5}],  # MIDI note; seconds
            "contour": {"step": 0.012, "segments": [...]},  # the pitch as sung, for the notes graph
            "key": "C", "mode": "major",
            "tempo": 100.0,        # 0.0 when it can't be measured
            "tuning_cents": -12,   # how far off A440 the hum was (already corrected in hz)
            "warnings": [...],     # problems with the recording, in words for the user
            "analysis": {...},     # the full process_audio result, only with keep_analysis
        }

    Raises:
        AudioInputError: the file can't be used
    """
    processor = AudioProcessor(target_sr=target_sr, debug=debug)
    analysis = processor.process_audio(filepath, detect_segments=True, extract_pitch=True, extract_volume=False, extract_spectral=False)
    notes, tuning, unpitched_share = _notes_from_pitch(analysis["pitch"], settings)
    melody = [{"hz": round(n["midi"], 2), "start": round(n["start"], 3), "duration": round(n["duration"], 3)} for n in notes]
    contour = pitch_contour(analysis["pitch"], tuning, settings)

    warnings = list(analysis["file"]["warnings"])
    if not melody:
        warnings.append("No clear notes were found. Try humming a little louder, one note at a time.")
    elif unpitched_share > UNPITCHED_SHARE:
        warnings.append("Much of the recording isn't a clear single tune (noise, talking, chords or music behind it?).")

    tempo = estimate_tempo_from_onsets([n["start"] for n in melody]) or _estimate_tempo(processor.audio, processor.sr)
    key, mode = _key_from_melody(melody) if melody else _estimate_key_and_mode(processor.audio, processor.sr)
    result = {
        "melody": melody,
        "contour": contour,
        "key": key,
        "mode": mode,
        "tempo": tempo,
        "tuning_cents": int(round(tuning * 100)),
        "warnings": warnings,
    }
    if keep_analysis:
        result["analysis"] = analysis
    return result


def quick_analyze(filepath: str, target_sr: int = 22050) -> Dict[str, Any]:
    """Headline numbers only: file facts, sound segments, pitch and volume summaries."""
    full_result = AudioProcessor(target_sr=target_sr).process_audio(filepath, extract_spectral=False)
    return {
        "file": full_result["file"],
        "segments": full_result["segments"],
        "pitch_summary": {
            key: full_result["pitch"].get(key, 0) for key in ("mean_hz", "median_hz", "min_hz", "max_hz", "voiced_frames")
        },
        "volume_summary": {
            key: full_result["volume"].get(key, 0) for key in ("mean_rms", "max_rms", "dynamic_range_db")
        },
        "processing_time": full_result["processing_time"],
    }


def extract_notes(
    filepath: str,
    target_sr: int = 22050,
    min_note_duration: Optional[float] = None,
    merge_gap: Optional[float] = None,
    debug: bool = False,
) -> list[dict[str, Any]]:
    """The notes of a WAV file with their loudness, for debugging and tests.

    Uses exactly the same note finding as ``analyze_audio_file`` (what the accompanist gets).

    Args:
        filepath: Path to the WAV file
        target_sr: Sample rate to analyse at
        min_note_duration: Shortest note in seconds (default NoteSettings.min_note_seconds)
        merge_gap: Silences shorter than this (seconds) don't end a note
            (default NoteSettings.bridge_gap_seconds)
        debug: Print each note

    Returns:
        Dicts with start, end, duration, volume (mean RMS), pitch_hz and midi
    """
    settings = DEFAULT_SETTINGS
    if min_note_duration is not None:
        settings = dataclasses.replace(settings, min_note_seconds=min_note_duration)
    if merge_gap is not None:
        settings = dataclasses.replace(settings, bridge_gap_seconds=merge_gap)

    result = AudioProcessor(target_sr=target_sr, debug=debug).process_audio(
        filepath, detect_segments=False, extract_pitch=True, extract_volume=False, extract_spectral=False
    )
    pitch = result["pitch"]
    notes, _, _ = _notes_from_pitch(pitch, settings)
    times = np.asarray(pitch["times"])
    loudness = 10 ** (np.asarray(pitch["rms_db"]) / 20)

    out = []
    for n in notes:
        inside = (times >= n["start"]) & (times < n["end"])
        out.append(
            {
                "start": round(n["start"], 3),
                "end": round(n["end"], 3),
                "duration": round(n["duration"], 3),
                "volume": round(float(np.mean(loudness[inside])) if inside.any() else 0.0, 6),
                "pitch_hz": round(float(librosa.midi_to_hz(n["midi"])), 1),
                "midi": round(n["midi"], 2),
            }
        )
    if debug:
        console_print(f"Extracted {len(out)} notes", "SUCCESS")
        for i, n in enumerate(out):
            console_print(f"  Note {i}: {n['start']:.2f}s-{n['end']:.2f}s midi={n['midi']:.2f} ({n['pitch_hz']:.1f}Hz)")
    return out


def clean_wav(filepath: str, output_path: Optional[str] = None, target_sr: int = 22050, debug: bool = False) -> str:
    """Write the cleaned recording (``filter_audio``: same length, so times still line up) as a
    16-bit mono WAV, to ``output_path`` or ``<name>_clean.wav`` next to the input."""
    processor = AudioProcessor(target_sr=target_sr, debug=debug)
    audio, sr = processor.load_wav(filepath)
    cleaned = processor.filter_audio(audio, sr)
    if output_path is None:
        base, ext = os.path.splitext(filepath)
        output_path = f"{base}_clean{ext or '.wav'}"
    sf.write(output_path, cleaned, sr, subtype="PCM_16")
    return output_path


def load_and_process_wav(filepath: str, target_sr: int = 22050, debug: bool = False, **kwargs) -> Dict[str, Any]:
    """Backward compatibility wrapper for ``analyze_audio_file``."""
    return analyze_audio_file(filepath, target_sr, debug=debug, **kwargs)


if __name__ == "__main__":
    # python -m hum.engine.audio.processor <file.wav>   (from backend/)
    if len(sys.argv) > 1:
        print(analyze_audio_file(sys.argv[1], debug=True))
    else:
        console_print("Usage: python -m hum.engine.audio.processor <path_to_wav_file>")
