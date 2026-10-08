"""Accompaniment styles: each style is a MIDI pattern generator.

A style takes a chord's voicing (list of MIDI pitches, root first) plus the
bar's start/duration in beats, and returns a list of
(pitch, start_beat, duration_beats, velocity) note events.
"""

from __future__ import annotations

import random
from typing import Callable

# A note event within a bar: pitch, start (beats), duration (beats), velocity.
NoteEvent = tuple[int, float, float, int]
StyleFn = Callable[[list[int], float, float, int], list[NoteEvent]]


def _root_third_fifth(pitches: list[int]) -> tuple[int, int, int]:
    """Return (root, third, fifth), tolerant of non-triads."""
    root = pitches[0]
    third = pitches[1] if len(pitches) > 1 else pitches[0]
    fifth = pitches[2] if len(pitches) > 2 else pitches[-1]
    return root, third, fifth


def piano_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Piano: bass -> chord -> chord (3 subdivisions).

    Beat 1: bass root (low). Beats 2-3: the full chord stabbed twice.
    """
    root, third, fifth = _root_third_fifth(pitches)
    bass = root - 12
    step = dur / 3
    events = [(bass, start, step, velocity)]
    for k in (1, 2):
        for p in pitches:
            events.append((p, start + k * step, step, velocity - 10))
    return events


def pop_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Pop: bass -> chord -> chord -> chord (4 subdivisions)."""
    root, third, fifth = _root_third_fifth(pitches)
    bass = root - 12
    step = dur / 4
    events = [(bass, start, step, velocity)]
    for k in (1, 2, 3):
        for p in pitches:
            events.append((p, start + k * step, step, velocity - 10))
    return events


def cinematic_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Cinematic: low bass + wide, sustained chord held for the whole bar."""
    root, third, fifth = _root_third_fifth(pitches)
    events: list[NoteEvent] = []
    # Low sustained bass, an octave below root.
    events.append((root - 12, start, dur, velocity))
    # Wide voicing: spread the chord tones with the fifth an octave up.
    wide = [root, third, fifth, fifth + 12]
    for p in wide:
        events.append((p, start, dur, velocity - 15))
    return events


def classical_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Classical: warm Alberti-style accompaniment with a sustained harmony.

    The previous version arpeggiated root-fifth-third-fifth as bare single
    notes, which emphasized hollow open fifths and rarely sounded the third —
    that reads as eerie/"creepy" even in a major key. Instead we now:

      * hold a soft, sustained triad under the whole bar so the *full* chord
        (including the warm major/minor third) always rings, and
      * lay a gentle Alberti pattern (low - high - mid - high) on top for
        motion, with a light dynamic swell.

    The `pitches` passed in should already be voice-led (see voice_leading).
    """
    root, third, fifth = _root_third_fifth(pitches)

    events: list[NoteEvent] = []

    # 1) Soft sustained triad for the whole bar, an octave DOWN, so the full
    #    harmony (with its third) always rings underneath without crowding the
    #    melody's register. This is what removes the hollow, eerie quality.
    pad_vel = max(1, velocity - 30)
    for p in (root, third, fifth):
        events.append((p - 12, start, dur, pad_vel))

    # 2) Gentle Alberti figuration in the accompaniment octave for motion:
    #    low-high-mid-high. Using the third as the "mid" keeps the warm
    #    major/minor color audible rather than hammering the open fifth.
    figure = [root, fifth, third, fifth]
    step = dur / len(figure)
    for k, p in enumerate(figure):
        v = velocity if k == 0 else max(1, velocity - 10)  # slight downbeat lift
        events.append((p, start + k * step, step * 0.95, v))

    return events


def _diatonic_seventh(root: int, third: int, fifth: int) -> int:
    """Pick a consonant 7th for the triad based on its quality.

    - major triad (third = +4)  -> major 7th  (+11): warm maj7 color
    - minor triad (third = +3)  -> minor 7th  (+10): standard m7
    - diminished (third +3, fifth +6) -> minor 7th (+10): half-diminished
    Falling back to a minor 7th keeps things smooth if intervals are unusual.
    """
    third_iv = (third - root) % 12
    fifth_iv = (fifth - root) % 12
    if third_iv == 4 and fifth_iv == 7:      # major triad
        return root + 11                      # maj7
    if third_iv == 3 and fifth_iv == 6:       # diminished triad
        return root + 10                      # -> half-diminished (m7b5)
    return root + 10                          # minor triad -> m7


# Swing ratio: an eighth-note pair is played long-short (2:1), i.e. the first
# eighth lasts a dotted-eighth-ish 2/3 of the beat, the second a triplet 1/3.
SWING_LONG = 2.0 / 3.0
SWING_SHORT = 1.0 / 3.0


# Rubato / humanization amounts (fractions of a beat / velocity units).
_RUBATO_TIME = 0.18      # max timing push-pull per note (in beats)
_RUBATO_VEL = 14         # max velocity jitter per note
_DROP_CHANCE = 0.25      # chance a given comp hit is dropped (breathing space)
_GHOST_CHANCE = 0.30     # chance of an extra syncopated "ghost" stab


def _humanize(pitch, at, dur, vel, *, bar_start, bar_end):
    """Apply rubato: nudge timing, vary velocity, keep the note inside the bar."""
    jitter = random.uniform(-_RUBATO_TIME, _RUBATO_TIME)
    at = at + jitter
    # Clamp so notes never spill before the bar or run past its end.
    at = max(bar_start, min(at, bar_end - 0.05))
    dur = max(0.05, min(dur * random.uniform(0.7, 1.25), bar_end - at))
    vel = max(1, min(127, int(vel + random.uniform(-_RUBATO_VEL, _RUBATO_VEL))))
    return (pitch, at, dur, vel)


def jazz_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Jazz: loose, rubato comping — swung, jumpy, and different every bar.

    Instead of a fixed grid, each hit is *humanized*: its timing is pushed or
    pulled off the beat (rubato), its velocity varies, some hits are randomly
    dropped for breathing space, and extra syncopated "ghost" stabs may appear.
    The underlying skeleton is still a walking bass + swung Charleston comp with
    dotted rhythm, but no two bars land the same way.

    The comp uses a consonant seventh matched to each chord's quality
    (maj7 / m7 / m7b5).
    """
    root, third, fifth = _root_third_fifth(pitches)
    seventh = _diatonic_seventh(root, third, fifth)
    comp = sorted([third, fifth, seventh])  # rootless third/fifth/seventh

    quarter = dur / 4
    bar_end = start + dur
    bass_vel = max(1, velocity - 6)
    comp_vel = max(1, velocity - 18)
    accent = max(1, velocity - 8)

    events: list[NoteEvent] = []

    # --- Walking bass: one per beat, each with a little rubato push-pull. ---
    walk = [root - 12, fifth - 12, third - 12, (root - 12) + 2]
    for k, bp in enumerate(walk):
        events.append(
            _humanize(bp, start + k * quarter, quarter * 0.6, bass_vel,
                      bar_start=start, bar_end=bar_end)
        )

    # --- Comp hits, each independently placed with rubato & random drops. ---
    # Nominal positions (in beats from bar start) with a base duration & velocity.
    comp_hits = [
        (0.0, quarter * SWING_LONG, accent),                       # beat 1 (long)
        (quarter + quarter * SWING_LONG, quarter * SWING_SHORT, comp_vel),  # & of 2
        (3 * quarter, quarter * 1.5, comp_vel),                    # beat 4 stab
    ]
    for offset, base_dur, base_vel in comp_hits:
        if random.random() < _DROP_CHANCE:
            continue  # leave a hole — rubato phrasing breathes
        for p in comp:
            events.append(
                _humanize(p, start + offset, base_dur, base_vel,
                          bar_start=start, bar_end=bar_end)
            )

    # --- Occasional extra ghost stab somewhere in the back half of the bar. ---
    if random.random() < _GHOST_CHANCE:
        ghost_at = start + random.uniform(1.5, 3.5) * quarter
        for p in comp:
            events.append(
                _humanize(p, ghost_at, quarter * SWING_SHORT, max(1, comp_vel - 12),
                          bar_start=start, bar_end=bar_end)
            )

    return events


def asian_folk_style(pitches, start, dur, velocity) -> list[NoteEvent]:
    """Asian folk: sparse, harp-like pentatonic arpeggio.

    Rolls up the chord tones (which have been snapped to a pentatonic scale
    upstream) with a gentle, open feel and a low sustained root.
    """
    root, third, fifth = _root_third_fifth(pitches)
    events: list[NoteEvent] = [
        # Low sustained root under the arpeggio.
        (root - 12, start, dur, velocity - 10),
    ]
    # Ascending arpeggio across the bar: root, third, fifth, octave.
    pattern = [root, third, fifth, root + 12]
    step = dur / len(pattern)
    for k, p in enumerate(pattern):
        events.append((p, start + k * step, step, velocity - 5))
    return events


STYLES: dict[str, StyleFn] = {
    "piano": piano_style,
    "pop": pop_style,
    "cinematic": cinematic_style,
    "classical": classical_style,
    "jazz": jazz_style,
    "asian_folk": asian_folk_style,
}

# Styles that require snapping notes to a specific scale, and which scale.
STYLE_SCALES: dict[str, str] = {
    "jazz": "jazz",
    "asian_folk": "pentatonic",
}
