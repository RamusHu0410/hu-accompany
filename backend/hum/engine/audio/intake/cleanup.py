"""basic-pitch's notes → one clean melody line. Only the note list changes; the audio is only read.

basic-pitch hears polyphonically and splits a sung note wherever its pitch wobbles. So the line is
rebuilt from its pitch contour (a pitch for every ~12 ms frame, a third of a semitone per bin):

1. one pitch per frame: the contour's strongest peak, unless that's a harmonic jump (an octave
   or so) from the last pitch and the last pitch is still there: then that, keeping ghosts out
2. the tuning offset: how far the whole hum sits off the semitone grid, taken out of every pitch.
   The contour is only good to about ten cents, so this is measured on the audio with pyin
3. legato: a new note starts where the pitch moves more than half a semitone plus a hysteresis
   and then holds steady (min_stable_ms); vibrato, drift and scoops never hold away, so they don't
4. repeated notes: a same-pitch note is split where its loudness dips (a re-attack)
5. fragments shorter than min_note_ms join the note they touch, or are dropped; octave ghosts join too
6. the guardrail: if that removed too much, the lightly filtered raw notes are used instead
"""

import math
from dataclasses import dataclass, field

import librosa
import numpy as np

from .config import CLEANUP, TRANSCRIPTION, CleanupSettings
from .transcribe import RawNote, Transcription

BINS_PER_SEMITONE = 3  # basic_pitch.constants.CONTOURS_BINS_PER_SEMITONE
LOWEST_MIDI = 21  # contour bin 0 is basic_pitch.constants.ANNOTATIONS_BASE_FREQUENCY, 27.5 Hz: A0
# ...but the model's contour peaks one bin (a third of a semitone) above that formula: a pure D3
# reads 50.34 instead of 50.00, and the same on every pitch tried (basic-pitch 0.4.0, ONNX model).
CONTOUR_BIN_OFFSET = 1
GHOST_INTERVALS = (12, 19, 24)  # octave, octave and a fifth, two octaves: where harmonics sit
GHOST_MAX_S = 0.2


@dataclass
class Note:
    start: float  # seconds
    end: float
    pitch: int  # MIDI note number
    velocity: int = 80


@dataclass
class Cleaned:
    notes: list[Note]
    tuning_cents: float
    fell_back: bool
    counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


def clean_melody(heard: Transcription, samples: np.ndarray, rate: int, settings: CleanupSettings = CLEANUP) -> Cleaned:
    times = heard.frame_times
    pitch, strength = pitch_track(heard.contour, settings)
    voiced = _voiced(times, heard.notes, strength, settings)
    tuning = tuning_offset(samples, rate)
    pitch = pitch - tuning  # in semitones, so a note's median rounds to the right MIDI number
    loudness = _loudness(samples, rate, times)

    notes = _segment(times, pitch, loudness, voiced, settings)
    notes = _join_fragments(notes, settings)
    for note in notes:
        note.velocity = _velocity(note, heard.notes)
    light = lightly_filtered(heard.notes, settings)
    counts = {"raw": len(heard.notes), "lightly_filtered": len(light), "clean": len(notes)}

    warnings = []
    if _sounds_polyphonic(heard.notes):
        warnings.append("It sounds like more than one voice or an instrument; ECKO followed the strongest line.")
    removed = 1 - len(notes) / len(light) if light else 0.0
    if len(notes) < settings.min_notes or removed > settings.max_removed_share:
        warnings.append("Some notes were hard to make out, so the melody follows the recording more loosely than usual.")
        return Cleaned(light, tuning * 100, True, counts, warnings)
    return Cleaned(notes, tuning * 100, False, counts, warnings)


def pitch_track(contour: np.ndarray, settings: CleanupSettings) -> tuple[np.ndarray, np.ndarray]:
    """A MIDI pitch for every frame (NaN where there's none) and how strong the contour was there."""
    low = _bin(librosa.hz_to_midi(TRANSCRIPTION.minimum_frequency))
    high = _bin(librosa.hz_to_midi(TRANSCRIPTION.maximum_frequency))
    region = contour[:, low : high + 1]
    pitch = np.full(len(contour), np.nan)
    strength = np.zeros(len(contour))
    last = None
    for i, row in enumerate(region):
        peak = row.max()
        if peak < settings.voicing_threshold:
            last = None
            continue
        best = int(row.argmax())
        if last is not None and _is_harmonic_jump(_midi(low + best) - last):
            peaks = [b for b in range(len(row)) if row[b] >= 0.6 * peak and row[b] == row[max(0, b - 1) : b + 2].max()]
            nearest = min(peaks, key=lambda b: abs(_midi(low + b) - last))
            if abs(_midi(low + nearest) - last) < 1:  # the note sung a moment ago is still sounding
                best = nearest
        pitch[i] = _midi(low + best + _peak_offset(row, best))
        strength[i] = row[best]
        last = pitch[i]
    return pitch, strength


def tuning_offset(samples: np.ndarray, rate: int) -> float:
    """How far the hum sits off the semitone grid, in semitones (-0.5 to 0.5): the average of how far
    each steady moment of its pitch (pyin, on the audio) is from the nearest semitone, taken around
    a circle so that +0.45 and -0.45 average to 0.5, not 0."""
    f0, voiced, _ = librosa.pyin(samples, fmin=TRANSCRIPTION.minimum_frequency, fmax=TRANSCRIPTION.maximum_frequency, sr=rate, frame_length=2048)
    midi = librosa.hz_to_midi(f0)
    steady = voiced & ~np.isnan(midi) & (np.abs(midi - _median(midi, 9)) < 0.25)  # no scoops or fast vibrato
    if steady.sum() < 5:
        return 0.0
    angle = 2 * np.pi * midi[steady]
    return float(math.atan2(np.mean(np.sin(angle)), np.mean(np.cos(angle))) / (2 * np.pi))


def lightly_filtered(raw: list[RawNote], settings: CleanupSettings = CLEANUP) -> list[Note]:
    """The guardrail's fallback: basic-pitch's notes with only the obvious removed. Fragments go; of
    notes sounding together only the strongest stays; a note running straight on at the same pitch joins."""
    kept: list[RawNote] = []
    for note in sorted(raw, key=lambda n: n.start):
        if note.end - note.start < settings.min_note_ms / 1000:
            continue
        if kept and note.start < kept[-1].end:
            if note.amplitude * (note.end - note.start) <= kept[-1].amplitude * (kept[-1].end - kept[-1].start):
                continue
            kept[-1] = RawNote(kept[-1].start, note.start, kept[-1].pitch, kept[-1].amplitude)
            if kept[-1].end - kept[-1].start < settings.min_note_ms / 1000:
                kept.pop()
        if kept and note.pitch == kept[-1].pitch and note.start - kept[-1].end < settings.bridge_gap_ms / 1000:
            kept[-1] = RawNote(kept[-1].start, note.end, note.pitch, max(note.amplitude, kept[-1].amplitude))
            continue
        kept.append(note)
    return [Note(n.start, n.end, n.pitch, _velocity_from(n.amplitude)) for n in kept]


def _segment(times, pitch, loudness, voiced, s: CleanupSettings) -> list[Note]:
    frame = float(np.median(np.diff(times)))
    stable = max(2, math.ceil(s.min_stable_ms / 1000 / frame))
    away = 0.5 + s.hysteresis_semitones
    spans = []
    for first, stop in _runs(voiced):
        start, held = first, [pitch[first]]
        for i in range(first + 1, stop):
            if abs(pitch[i] - np.median(held)) <= away:
                held.append(pitch[i])
                continue
            recent = pitch[i - stable + 1 : i + 1]
            if i - stable + 1 > start and np.all(np.abs(recent - np.median(held)) > away) and np.ptp(recent) <= s.stable_spread_semitones:
                moved = i - stable + 1
                while moved - 1 > start and abs(pitch[moved - 1] - np.median(held)) > away:
                    moved -= 1  # the change began where the pitch first left the held note
                spans.append((start, moved))
                start, held = moved, list(recent)
        spans.append((start, stop))
    spans = [piece for span in spans for piece in _split_at_dips(span, loudness, frame, s)]
    # bridged silences are voiced but have no pitch: nanmedian skips them
    return [Note(float(times[a]), float(times[b - 1] + frame), int(round(np.nanmedian(pitch[a:b])))) for a, b in spans]


def _split_at_dips(span, loudness, frame, s: CleanupSettings):
    """A note re-attacked at the same pitch: split it where its loudness dips well below its own. The
    first part ends where the dip begins; the repeat starts in the middle of the dip, where it's sung."""
    a, b = span
    edge = math.ceil(s.min_note_ms / 1000 / frame)
    level = np.median(loudness[a:b])
    low = loudness < s.dip_ratio * level
    for dip_start, dip_stop in _runs(low[a:b]):
        dip_start, dip_stop = a + dip_start, a + dip_stop
        if (dip_stop - dip_start) * frame >= s.min_dip_ms / 1000 and dip_start - a >= edge and b - dip_stop >= edge:
            return [(a, dip_start), *_split_at_dips(((dip_start + dip_stop) // 2, b), loudness, frame, s)]
    return [span]


def _join_fragments(notes: list[Note], s: CleanupSettings) -> list[Note]:
    """Fragments and octave ghosts join the note they touch (the longer neighbour); lone fragments go."""
    touching = s.bridge_gap_ms / 1000
    changed = True
    while changed:
        changed = False
        for i, note in enumerate(notes):
            length = note.end - note.start
            neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(notes) and _gap(notes[j], note) < touching]
            ghost = length < GHOST_MAX_S and any(_is_harmonic_jump(notes[j].pitch - note.pitch, 1) for j in neighbours)
            if length >= s.min_note_ms / 1000 and not ghost:
                continue
            if neighbours:
                host = notes[max(neighbours, key=lambda j: notes[j].end - notes[j].start)]
                host.start, host.end = min(host.start, note.start), max(host.end, note.end)
            del notes[i]
            changed = True
            break
    return notes


def _voiced(times, raw: list[RawNote], strength, s: CleanupSettings) -> np.ndarray:
    """Frames inside one of basic-pitch's notes with a pitch in the contour; tiny silences bridged."""
    inside = np.zeros(len(times), dtype=bool)
    for note in raw:
        inside |= (times >= note.start) & (times < note.end)
    voiced = inside & (strength > 0)
    frame = float(np.median(np.diff(times)))
    for a, b in _runs(~voiced):
        if 0 < a and b < len(voiced) and (b - a) * frame < s.bridge_gap_ms / 1000:
            voiced[a:b] = True
    return voiced


def _loudness(samples, rate, times) -> np.ndarray:
    hop = 256
    rms = librosa.feature.rms(y=samples, frame_length=1024, hop_length=hop)[0]
    return np.interp(times, librosa.frames_to_time(np.arange(len(rms)), sr=rate, hop_length=hop), rms)


def _sounds_polyphonic(raw: list[RawNote]) -> bool:
    """More than a quarter of the sounding time has two notes at once that aren't harmonics of each other."""
    sounding = sum(n.end - n.start for n in raw)
    together = 0.0
    for i, a in enumerate(raw):
        for b in raw[i + 1 :]:
            overlap = min(a.end, b.end) - max(a.start, b.start)
            if overlap > 0 and abs(a.pitch - b.pitch) not in (0, *GHOST_INTERVALS, 28, 31, 36):
                together += overlap
    return sounding > 0 and together / sounding > 0.25


def _velocity(note: Note, raw: list[RawNote]) -> int:
    loudest = max((n.amplitude for n in raw if n.start < note.end and n.end > note.start), default=0.5)
    return _velocity_from(loudest)


def _velocity_from(amplitude: float) -> int:
    return int(np.clip(round(40 + 80 * amplitude), 1, 127))


def _is_harmonic_jump(semitones: float, within: float = 0.5) -> bool:
    """An octave, octave and a fifth or two octaves, give or take `within` (a ghost can round a semitone off)."""
    return any(abs(abs(semitones) - interval) <= within for interval in GHOST_INTERVALS)


def _gap(a: Note, b: Note) -> float:
    return max(b.start - a.end, a.start - b.end)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, stop) of every run of True."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _median(values: np.ndarray, width: int) -> np.ndarray:
    padded = np.pad(values, width // 2, mode="edge")
    return np.array([np.nanmedian(padded[i : i + width]) if not np.all(np.isnan(padded[i : i + width])) else np.nan for i in range(len(values))])


def _peak_offset(row: np.ndarray, b: int) -> float:
    """Where the true peak lies between bins (parabolic interpolation), -0.5 to 0.5."""
    if b == 0 or b == len(row) - 1:
        return 0.0
    left, mid, right = row[b - 1], row[b], row[b + 1]
    bend = left - 2 * mid + right
    return float(np.clip(0.5 * (left - right) / bend, -0.5, 0.5)) if bend < 0 else 0.0


def _bin(midi: float) -> int:
    return int(round((midi - LOWEST_MIDI) * BINS_PER_SEMITONE)) + CONTOUR_BIN_OFFSET


def _midi(contour_bin: float) -> float:
    return LOWEST_MIDI + (contour_bin - CONTOUR_BIN_OFFSET) / BINS_PER_SEMITONE
