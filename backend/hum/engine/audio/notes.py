"""Turns a frame-by-frame pitch track into notes: where each note starts and ends, and which note it is.

The earlier version only started a new note where the recording went quiet (librosa's
"30 dB below the loudest moment"). A legato scale, a fast run, repeated notes, or any recording
with a little background noise therefore came out as one long note with a median pitch.
Here a note ends for any of three reasons, judged on the pYIN track (~12 ms per frame):

    gap     the sound stops (unvoiced or under the noise gate): for longer than a breath, or for
            any time at all when the pitch on the two sides differs
    pitch   the average pitch just after a moment differs from the average just before it by
            more than ``split_semitones``. The averages span about one vibrato cycle, so a
            wavering note cancels itself out while a step to a new note doesn't
    dip     the loudness dips and comes back by ``dip_db`` (a re-sung note at the same pitch)

Fragments too short to be a note, and short pieces whose pitch slides rather than holds (a scoop
into a note, a slide between two), are joined to the note they touch, not thrown away. Pitches are measured on the note's steady middle, after correcting the
singer's overall tuning (``estimate_tuning``), so a hum that is consistently a bit flat still
lands on the right notes.

Everything here is plain numpy on arrays, so it can be tested without any audio.
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks


@dataclass(frozen=True)
class NoteSettings:
    min_note_seconds: float = 0.08  # a 16th note at 180 BPM; anything shorter is a fragment
    bridge_gap_seconds: float = 0.05  # silences shorter than this don't end a note
    split_semitones: float = 0.7  # a pitch change bigger than this (short of a semitone) starts a new note
    change_window_seconds: float = 0.18  # the averages compared around each moment: one 5.5 Hz vibrato cycle
    dip_db: float = 5.0  # a loudness dip this deep, inside one pitch, re-starts the note
    gate_above_floor_db: float = 8.0  # sound must be this far over the noise floor to count
    gate_below_peak_db: float = 12.0  # ...but the gate never sits closer than this to the loudest part
    gate_range_db: float = 45.0  # ...and never further than this under it (digital silence has no floor)
    smooth_seconds: float = 0.06  # median smoothing of the pitch track (single-frame glitches)
    octave_window_seconds: float = 0.15  # frames an octave off from their surroundings are pYIN errors
    steady_fraction: float = 0.6  # the note's pitch is measured on this middle share of its frames
    min_tuning_confidence: float = 0.3  # below this the tuning estimate is noise and isn't applied
    glide_semitones: float = 1.0  # a short piece whose pitch moves this far from start to end slides
    glide_max_seconds: float = 0.3  # ...longer than this, it's a (badly held) note


DEFAULT_SETTINGS = NoteSettings()


def noise_gate(rms_db: np.ndarray, settings: NoteSettings = DEFAULT_SETTINGS) -> float:
    """The loudness (dB) a frame needs to count as sound, set from the recording's own noise floor
    rather than from its peak, so a noisy room doesn't turn the whole clip into one note."""
    finite = rms_db[np.isfinite(rms_db)]
    if finite.size == 0:
        return np.inf
    floor = np.percentile(finite, 10)
    peak = np.percentile(finite, 99)
    gate = min(floor + settings.gate_above_floor_db, peak - settings.gate_below_peak_db)
    return float(max(gate, peak - settings.gate_range_db))


def estimate_tuning(notes: list[dict], settings: NoteSettings = DEFAULT_SETTINGS) -> float:
    """How far (in semitones, -0.5..0.5) the singer sits from A440 tuning overall.

    A circular mean, weighted by duration, of each note's distance from the nearest semitone, so
    59.6 and 60.4 average to "in tune", not to a quarter tone off. It's measured on whole notes,
    not frames: vibrato spends most of its time at the extremes of its swing, so frames of an
    in-tune note with a half-semitone vibrato look a quarter tone off. Returns 0 when the notes
    disagree too much to tell, rather than applying a guess.
    """
    if not notes:
        return 0.0
    midi = np.array([n["midi"] for n in notes])
    weights = np.array([n["duration"] for n in notes])
    vector = np.sum(weights * np.exp(2j * np.pi * midi)) / np.sum(weights)
    if np.abs(vector) < settings.min_tuning_confidence:
        return 0.0
    return float(np.angle(vector) / (2 * np.pi))


def segment_notes(
    times: np.ndarray,
    midi: np.ndarray,
    active: np.ndarray,
    rms_db: np.ndarray | None = None,
    settings: NoteSettings = DEFAULT_SETTINGS,
) -> list[dict]:
    """Notes from a pitch track.

    Args:
        times: Frame times in seconds (evenly spaced).
        midi: Fractional MIDI pitch per frame (NaN where unpitched).
        active: Whether each frame is sung sound (voiced and above the noise gate).
        rms_db: Loudness per frame, for splitting re-sung notes of the same pitch. Optional.

    Returns:
        Dicts with start, end, duration (seconds), midi (fractional) and ended_by
        ("gap", "pitch" or "dip": what separated it from the next note).
    """
    times = np.asarray(times, dtype=float)
    midi = np.asarray(midi, dtype=float)
    active = np.asarray(active, dtype=bool) & np.isfinite(midi)
    if times.size == 0 or not active.any():
        return []
    hop = float(np.median(np.diff(times))) if times.size > 1 else 0.01
    frames = lambda seconds: max(1, int(round(seconds / hop)))  # noqa: E731

    midi = _fold_octave_errors(midi, active, frames(settings.octave_window_seconds))
    smooth = _smooth_runs(midi, active, frames(settings.smooth_seconds))

    pieces = []
    for start, stop in _sounding_runs(active, smooth, frames(settings.bridge_gap_seconds), frames(settings.change_window_seconds), settings):
        pieces += _split_on_pitch(
            start, stop, smooth, active, frames(settings.change_window_seconds), frames(settings.min_note_seconds), settings
        )
    if rms_db is not None:
        rms_db = np.asarray(rms_db, dtype=float)
        pieces = [part for piece in pieces for part in _split_on_dips(piece, rms_db, frames(settings.min_note_seconds), settings)]

    notes = [_note(start, stop, cause, times, midi, active, hop, settings) for start, stop, cause in pieces]
    return _absorb_fragments([n for n in notes if n is not None], settings)


def estimate_tempo_from_onsets(onsets: list[float], low: float = 70.0, high: float = 140.0) -> float:
    """The tempo (BPM) whose eighth-note grid best fits the time between note onsets, or 0.0 when
    there are too few notes to tell. librosa's beat tracker needs percussive attacks and returns
    0 for most hums; the gaps between the notes someone hummed are a far steadier clue.

    Searches one octave of tempos (70-140), so a tune can't be read at both double and half speed,
    with a gentle pull toward 100 BPM to break near-ties.
    """
    onsets = np.sort(np.asarray(onsets, dtype=float))
    gaps = np.diff(onsets)
    gaps = gaps[gaps > 0.08]
    if gaps.size < 2:
        return 0.0
    best_tempo, best_score = 0.0, -np.inf
    for tempo in np.arange(low, high, 0.5):
        in_beats = gaps * tempo / 60.0
        off_grid = np.abs(in_beats - np.round(in_beats * 2) / 2)  # distance to the nearest eighth
        score = np.mean(np.exp(-0.5 * (off_grid / 0.08) ** 2)) - 0.05 * abs(np.log2(tempo / 100.0))
        if score > best_score:
            best_tempo, best_score = float(tempo), score
    return best_tempo


# --------------------------------------------------------------------------- helpers


def _fold_octave_errors(midi: np.ndarray, active: np.ndarray, window: int) -> np.ndarray:
    """pYIN sometimes jumps an octave for a few frames. A frame about 12 semitones away from the
    median of its neighbourhood is moved back by an octave."""
    fixed = midi.copy()
    values = np.where(active, midi, np.nan)
    half = window // 2
    for i in np.flatnonzero(active):
        around = values[max(0, i - half) : i + half + 1]
        local = np.nanmedian(around)
        offset = fixed[i] - local
        if abs(abs(offset) - 12) < 1.0:
            fixed[i] -= 12 * np.sign(offset)
    return fixed


def _smooth_runs(midi: np.ndarray, active: np.ndarray, size: int) -> np.ndarray:
    """Median-smoothed pitch within each stretch of sound (never across a silence)."""
    smooth = np.full_like(midi, np.nan)
    size = size if size % 2 else size + 1
    for start, stop in _runs(active):
        smooth[start:stop] = median_filter(midi[start:stop], size=min(size, stop - start), mode="nearest")
    return smooth


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, stop) index ranges where mask is True."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


# Public name for the pitch contour, which needs the same runs of sounding frames.
sounding_runs = _runs


def _sounding_runs(active, smooth, bridge, window, settings) -> list[tuple[int, int]]:
    """Stretches of sound. Two are joined across a silence shorter than ``bridge`` frames (the
    pitch tracker losing a breathy tone for a moment) only if the pitch is the same on both sides:
    in a fast run the brief gaps between notes are the clearest boundaries there are."""
    runs = _runs(active)
    joined = [list(runs[0])]
    for start, stop in runs[1:]:
        before = smooth[max(joined[-1][0], joined[-1][1] - window) : joined[-1][1]]
        after = smooth[start : min(stop, start + window)]
        same_pitch = abs(np.nanmedian(after) - np.nanmedian(before)) <= settings.split_semitones
        if start - joined[-1][1] < bridge and same_pitch:
            joined[-1][1] = stop
        else:
            joined.append([start, stop])
    return [(start, stop) for start, stop in joined]


def _split_on_pitch(start, stop, smooth, active, window, min_frames, settings):
    """Pieces of one stretch of sound, split where the pitch steps somewhere new.

    For every frame, compare the mean pitch of the ``window`` frames after it with the mean of the
    ``window`` frames before it. A step to a new note makes that difference peak right at the
    step; vibrato averages out over a window about one cycle long. A slide makes a plateau, which
    splits once in its middle.
    """
    values = smooth[start:stop]
    ok = active[start:stop] & np.isfinite(values)
    total = np.concatenate([[0.0], np.cumsum(np.where(ok, values, 0.0))])
    count = np.concatenate([[0], np.cumsum(ok)])
    size = stop - start
    i = np.arange(size)
    before, after = np.maximum(0, i - window), np.minimum(size, i + window)
    n_before, n_after = count[i] - count[before], count[after] - count[i]
    need = max(2, window // 2)  # half a vibrato cycle either side, or the swing reads as a step
    enough = (n_before >= need) & (n_after >= need)
    change = np.zeros(size)
    change[enough] = np.abs(
        (total[after] - total[i])[enough] / n_after[enough] - (total[i] - total[before])[enough] / n_before[enough]
    )
    steps, _ = find_peaks(change, height=settings.split_semitones, distance=max(1, min_frames))
    bounds = [start, *(start + int(step) for step in steps), stop]
    return [(a, b, "pitch" if b != stop else "gap") for a, b in zip(bounds[:-1], bounds[1:])]


def _split_on_dips(piece, rms_db, min_frames, settings):
    """Split a piece where the loudness dips and recovers, so "da-da-da" on one pitch is three notes."""
    start, stop, cause = piece
    loudness = np.nan_to_num(rms_db[start:stop], nan=-120.0)
    if loudness.size < 2 * min_frames:
        return [piece]
    dips, _ = find_peaks(-loudness, prominence=settings.dip_db)
    cuts = []
    last = 0
    for dip in dips:
        if dip - last >= min_frames and loudness.size - dip >= min_frames:
            cuts.append(dip)
            last = dip
    if not cuts:
        return [piece]
    bounds = [0, *cuts, loudness.size]
    return [
        (start + a, start + b, "dip" if b != loudness.size else cause)
        for a, b in zip(bounds[:-1], bounds[1:])
    ]


def _note(start, stop, cause, times, midi, active, hop, settings):
    sounding = np.flatnonzero(active[start:stop]) + start
    if sounding.size == 0:
        return None
    first, last = sounding[0], sounding[-1]
    # the steady middle: leave out the scoop in and the fall-off at the end
    trim = int(sounding.size * (1 - settings.steady_fraction) / 2)
    steady = sounding[trim : sounding.size - trim] if sounding.size - 2 * trim >= 3 else sounding
    begin, end = float(times[first]), float(times[last] + hop)
    third = max(1, sounding.size // 3)
    drift = abs(np.median(midi[sounding[-third:]]) - np.median(midi[sounding[:third]]))
    glide = drift > settings.glide_semitones and end - begin < settings.glide_max_seconds
    return {"start": begin, "end": end, "duration": end - begin, "midi": float(np.median(midi[steady])), "ended_by": cause, "glide": glide}


def _absorb_fragments(notes: list[dict], settings: NoteSettings) -> list[dict]:
    """Join fragments and glides onto a note they touch (the next one first: a scoop leads into
    its note). A fragment that touches nothing is a blip and is dropped; a glide that touches
    nothing is kept, as the only note there is."""
    notes = [dict(n) for n in notes]
    touching = lambda a, b: b["start"] - a["end"] <= settings.bridge_gap_seconds  # noqa: E731
    i = 0
    while i < len(notes):
        note = notes[i]
        fragment = note["duration"] < settings.min_note_seconds
        has_neighbour = (i + 1 < len(notes) and touching(note, notes[i + 1])) or (i > 0 and touching(notes[i - 1], note))
        if not fragment and not (note["glide"] and has_neighbour):
            i += 1
            continue
        if i + 1 < len(notes) and touching(note, notes[i + 1]):
            notes[i + 1]["start"] = note["start"]
            notes[i + 1]["duration"] = notes[i + 1]["end"] - note["start"]
        elif i > 0 and touching(notes[i - 1], note):
            notes[i - 1]["end"] = note["end"]
            notes[i - 1]["duration"] = note["end"] - notes[i - 1]["start"]
            notes[i - 1]["ended_by"] = note["ended_by"]
        del notes[i]
    for note in notes:
        del note["glide"]
    return notes
