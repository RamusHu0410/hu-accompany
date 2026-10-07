"""Generate a chord progression from a melody (one chord per bar).

With rules enabled (default), the progression is chosen by a Viterbi dynamic
program that maximizes melody-fit plus transition quality across the whole
sequence, so chord choices are context-aware (see progression_rules).
"""

from __future__ import annotations

from copy import copy

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_candidates import get_candidates
from hum.engine.accompanist.music.chord_scoring import score_chord, _chord_pitch_classes
from hum.engine.accompanist.music.chord_selection import choose_best_chord, _root_pc
from hum.engine.accompanist.music.progression_rules import transition_score
from hum.engine.accompanist.music.segmentation import (
    segment_by_slot,
    DEFAULT_BEATS_PER_BAR,
)


def _melody_fit(chord: Chord, pitches: list[int], key: str, mode: str) -> float:
    """Melody-fit score for a chord in one bar (higher = better fit).

    Adds small tie-breakers (root-in-melody, coverage) as fractional bonuses so
    they never outweigh a full rule/fit point.
    """
    if not pitches:
        # No melody constraint this bar; slight bias toward the tonic (degree
        # handled by transition rules) — return neutral fit.
        return 0.0
    melody_pcs = {n % 12 for n in pitches}
    base = score_chord(chord, pitches, key, mode)
    root_in_melody = 1 if _root_pc(chord) in melody_pcs else 0
    coverage = len(melody_pcs & _chord_pitch_classes(chord))
    return base + 0.3 * root_in_melody + 0.1 * coverage


def generate_progression(
    melody_notes: list[dict],
    key: str = "C",
    mode: str = "major",
    beats_per_bar: float = DEFAULT_BEATS_PER_BAR,
    num_bars: int | None = None,
    use_rules: bool = True,
    chords_per_bar: int = 2,
) -> list[Chord]:
    """Build a chord progression that follows the melody's harmonic rhythm.

    The melody is segmented at `chords_per_bar` slots per bar, a chord is chosen
    per slot (so the harmony can change mid-bar when the melody does), and then
    adjacent identical chords are merged back into longer chords. This fixes
    bars whose notes belong to two different chords (e.g. Twinkle's "F F E E"),
    which a single per-bar chord could not match.

    Args:
        melody_notes: Notes as dicts with "pitch"/"start"/"duration".
        key: Tonic of the surrounding key.
        mode: "major" or "minor".
        beats_per_bar: Bar length in quarter lengths.
        num_bars: Force this many bars (else inferred).
        use_rules: If True, apply progression rules (repeat penalty, common
            transitions, cadence) via a Viterbi DP. If False, pick each slot's
            best chord greedily and independently.
        chords_per_bar: Harmonic-rhythm resolution. 1 = one chord per bar,
            2 = allow a change at the half-bar (default), etc.

    Returns:
        A list of Chord objects with start/duration spanning each held chord.
    """
    chords_per_bar = max(1, int(chords_per_bar))

    # Pass 1: choose one chord per bar over the whole piece (context-aware DP).
    bar_segments = segment_by_slot(melody_notes, beats_per_bar, num_bars)
    if not bar_segments:
        return []
    if use_rules:
        bar_chords = _viterbi(bar_segments, key, mode)
    else:
        bar_chords = [
            choose_best_chord([n["pitch"] for n in seg], key, mode)
            if seg else _tonic_chord(key, mode)
            for seg in bar_segments
        ]

    # Pass 2: only subdivide a bar whose single chord poorly fits its melody.
    # Bars that a whole-bar chord already matches stay as one chord — so clean,
    # unambiguous bars are never split needlessly.
    progression: list[Chord] = []
    for i, bar_chord in enumerate(bar_chords):
        bar_start = i * beats_per_bar
        bar_notes_i = bar_segments[i]

        if chords_per_bar > 1 and _bar_needs_split(bar_chord, bar_notes_i, key, mode):
            progression.extend(
                _split_bar(bar_notes_i, bar_start, beats_per_bar,
                           chords_per_bar, key, mode)
            )
        else:
            chord = copy(bar_chord)
            chord.start = bar_start
            chord.duration = beats_per_bar
            progression.append(chord)

    return progression


def _bar_needs_split(chord: Chord, notes: list[dict], key: str, mode: str) -> bool:
    """True if the whole-bar chord clashes with too much of the bar's melody."""
    if not notes:
        return False
    chord_pcs = _chord_pitch_classes(chord)
    clashes = sum(1 for n in notes if n["pitch"] % 12 not in chord_pcs)
    # Split only when most of the bar's notes don't belong to the chord.
    return clashes > len(notes) / 2


def _split_bar(notes, bar_start, beats_per_bar, chords_per_bar, key, mode):
    """Re-harmonize one bar at finer resolution, merging identical slots."""
    slot_beats = beats_per_bar / chords_per_bar
    # Local, bar-relative slots.
    rel = [
        {"pitch": n["pitch"], "start": n["start"] - bar_start,
         "duration": n["duration"]}
        for n in notes
    ]
    slot_segs = segment_by_slot(rel, slot_beats, chords_per_bar)
    slot_chords = [
        choose_best_chord([n["pitch"] for n in seg], key, mode)
        if seg else _tonic_chord(key, mode)
        for seg in slot_segs
    ]

    out: list[Chord] = []
    slot = 0
    while slot < len(slot_chords):
        sym = slot_chords[slot].symbol
        run = 1
        while slot + run < len(slot_chords) and slot_chords[slot + run].symbol == sym:
            run += 1
        chord = copy(slot_chords[slot])
        chord.start = bar_start + slot * slot_beats
        chord.duration = run * slot_beats
        out.append(chord)
        slot += run
    return out


def _viterbi(segments: list[list[dict]], key: str, mode: str) -> list[Chord]:
    """Best chord path maximizing melody-fit + transition scores."""
    candidates = get_candidates(key, mode)
    n = len(segments)
    if n == 0:
        return []

    pitches_per_bar = [[note["pitch"] for note in seg] for seg in segments]

    # best[i][c] = (best cumulative score ending in candidate c at bar i,
    #               backpointer to candidate index at bar i-1)
    fit0 = [_melody_fit(c, pitches_per_bar[0], key, mode) for c in candidates]
    best = [(fit0[c], -1) for c in range(len(candidates))]

    back: list[list[int]] = [[-1] * len(candidates)]

    for i in range(1, n):
        new_best = []
        bp_row = []
        for cj, cur in enumerate(candidates):
            fit = _melody_fit(cur, pitches_per_bar[i], key, mode)
            is_final = i == n - 1
            best_prev_score = None
            best_prev_idx = -1
            for ci, prev in enumerate(candidates):
                trans = transition_score(prev, cur, key, mode, is_final=is_final)
                total = best[ci][0] + trans + fit
                if best_prev_score is None or total > best_prev_score:
                    best_prev_score = total
                    best_prev_idx = ci
            new_best.append((best_prev_score, best_prev_idx))
            bp_row.append(best_prev_idx)
        best = new_best
        back.append(bp_row)

    # Find best final state.
    final_idx = max(range(len(candidates)), key=lambda c: best[c][0])

    # Backtrack.
    path_indices = [0] * n
    path_indices[n - 1] = final_idx
    for i in range(n - 1, 0, -1):
        path_indices[i - 1] = back[i][path_indices[i]]

    return [candidates[idx] for idx in path_indices]


def _tonic_chord(key: str, mode: str) -> Chord:
    quality = "minor" if mode == "minor" else "major"
    return Chord(root=key, quality=quality)
