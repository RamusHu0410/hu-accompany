"""Render chord progressions into MIDI accompaniment.

Supports two styles:
  * "block"  - all chord tones sound together for the whole bar.
  * "broken" - a broken-chord (arpeggio) pattern: root, fifth, third, fifth.
"""

from __future__ import annotations

import pretty_midi

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_to_midi import chord_pitches
from hum.engine.accompanist.music.styles import STYLES
from hum.engine.accompanist.music.voice_leading import lead_voices

DEFAULT_PROGRAM = 81      # Lead 2 (sawtooth) — default synth accompaniment
DEFAULT_VELOCITY = 70     # accompaniment base — clearly under the melody
# Melody stays in the synth family but a distinct voice from the accompaniment,
# so it doesn't blend in where a chord tone shares its pitch. It also plays louder.
MELODY_PROGRAM = 80       # Lead 1 (square)
MELODY_VELOCITY = 127     # loudest — the melody line leads
# The accompaniment stacks several chord tones at once, so at equal settings it
# is nearly as loud as the single-note melody (only ~1-3 dB quieter when
# rendered). Its velocity and channel volume (CC7) are pulled down so the
# melody sits roughly 7-10 dB on top and is easy to follow. The melody keeps
# CC7 below the 127 ceiling so talk mode's "loud" lead level can still raise it.
ACCOMP_CHANNEL_VOLUME = 85
MELODY_CHANNEL_VOLUME = 110
ACCOMP_VELOCITY_SCALE = 1.0
# Force every accompaniment note to this fixed velocity so per-style dynamic
# reductions stay consistent, while sitting below the melody. Set to None to
# keep each style's own internal dynamics.
ACCOMP_FIXED_VELOCITY = DEFAULT_VELOCITY
# When a melody is provided, keep every chord tone strictly below the
# melody's lowest note within that bar (see `_pitches_below_melody`), so the
# accompaniment never sits in or above the melody's register and mask it.
MIN_ACCOMPANIMENT_PITCH = 45  # never drop chords below this (A2) chasing separation
# Hard floor for any single accompaniment note (bass notes included). Anything
# lower is raised by octaves, so the line never sinks into a muddy rumble.
LOWEST_ACCOMPANIMENT_NOTE = 36  # C2
# A note that runs right up to the exact instant the next note attacks gets
# cut off mid-decay by that retrigger, instead of ringing out — it never
# audibly "resonates". Shaving a small silent gap off the end gives the
# synth's release/decay phase somewhere to finish. Never crosses a bar
# boundary (that invariant is load-bearing elsewhere), only shrinks toward it.
NOTE_RELEASE_SECONDS = 0.03

# Named General MIDI instruments (program numbers) for convenience.
INSTRUMENTS: dict[str, int] = {
    "synth": 81,             # Lead 2 (sawtooth) — default
    "synth_pad": 88,         # Pad 1 (new age) — softer sustained synth
    "piano": 0,              # Acoustic Grand Piano
    "guitar": 24,           # Acoustic Guitar (nylon)
    "guitar_steel": 25,     # Acoustic Guitar (steel)
    "guitar_jazz": 26,      # Electric Guitar (jazz)
    "guitar_clean": 27,     # Electric Guitar (clean)
    "electric_piano": 4,    # Electric Piano 1
    "strings": 48,          # String Ensemble
    "sax": 66,              # Tenor Sax
}
# Broken-chord order expressed as indices into the [root, third, fifth] triad.
# root, fifth, third, fifth  ->  e.g. C: C G E G
BROKEN_PATTERN = [0, 2, 1, 2]


def _seconds_per_beat(tempo: float) -> float:
    return 60.0 / tempo


def _trim_for_release(
    start_seconds: float, end_seconds: float, release_seconds: float = NOTE_RELEASE_SECONDS
) -> float:
    """Return an end time shortened by a small release gap, so the note's
    natural decay isn't cut off by the next note's attack. Never eats more
    than a quarter of the note's own length, so short notes (fast broken-
    chord steps) aren't gutted."""
    duration = end_seconds - start_seconds
    gap = min(release_seconds, duration * 0.25)
    return end_seconds - max(gap, 0.0)


def _melody_min_pitch_in_range(
    melody_notes: list[dict], start_beat: float, end_beat: float
) -> int | None:
    """Lowest melody pitch sounding during [start_beat, end_beat), or None if
    no melody note overlaps that range (e.g. the melody has a rest there)."""
    overlapping = [
        n["pitch"]
        for n in melody_notes
        if n["start"] < end_beat and n["start"] + n["duration"] > start_beat
    ]
    return min(overlapping) if overlapping else None


def _pitches_below_melody(
    pitches: list[int], melody_min_pitch: int | None, floor: int = MIN_ACCOMPANIMENT_PITCH
) -> list[int]:
    """Drop `pitches` by whole octaves until every one sits below
    `melody_min_pitch`, so the accompaniment never masks the melody note it's
    under. A no-op when there's no melody note to stay clear of, and gives up
    (returns pitches as last shifted) if `floor` would be crossed first, so a
    freak low melody note can't push the chord into subaudible territory.
    """
    if melody_min_pitch is None or not pitches:
        return pitches
    shifted = list(pitches)
    while max(shifted) >= melody_min_pitch and min(shifted) - 12 >= floor:
        shifted = [p - 12 for p in shifted]
    return shifted


def render_accompaniment(
    chords: list[Chord],
    path: str,
    *,
    style: str = "broken",
    tempo: float = 120.0,
    beats_per_bar: float = 4.0,
    octave: int = 3,
    melody_notes: list[dict] | None = None,
    program: int = DEFAULT_PROGRAM,
    melody_program: int = MELODY_PROGRAM,
    velocity: int = DEFAULT_VELOCITY,
) -> str:
    """Render a chord progression (optionally with melody) to a MIDI file.

    Chord `start`/`duration` are interpreted in beats (quarter lengths). If a
    chord has no timing set, bars are laid out sequentially using
    `beats_per_bar`.

    Args:
        chords: The progression.
        path: Output .mid path.
        style: "block" or "broken".
        tempo: BPM (also written to the MIDI header).
        beats_per_bar: Bar length in beats, used for fallback layout and for
            splitting broken-chord patterns.
        octave: Root octave for the chord voicing.
        melody_notes: Optional melody dicts (pitch/start/duration in beats) to
            include on a separate track.
        program: GM program for the accompaniment instrument.
        velocity: Note velocity.

    Returns:
        The output path.
    """
    spb = _seconds_per_beat(tempo)
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    acc = pretty_midi.Instrument(program=program)

    # For named styles, pre-compute voicings. Classical uses voice leading so
    # chords connect smoothly; others use plain root-position voicings.
    style_fn = STYLES.get(style)
    voicings: list[list[int]] | None = None
    if style_fn is not None:
        if style == "classical":
            voicings = lead_voices(chords, octave=octave)
        else:
            voicings = [chord_pitches(c, octave) for c in chords]

    for i, chord in enumerate(chords):
        # Determine bar timing in beats.
        start_beat = chord.start if chord.duration else i * beats_per_bar
        dur_beats = chord.duration or beats_per_bar
        bar_end_beat = start_beat + dur_beats

        # Keep the accompaniment below the melody's register for this bar.
        # Only touches anything when a melody was actually passed in; with no
        # melody_notes this is a no-op and behavior is unchanged.
        melody_floor = (
            _melody_min_pitch_in_range(melody_notes, start_beat, bar_end_beat)
            if melody_notes
            else None
        )

        if style_fn is not None:
            pitches = _pitches_below_melody(voicings[i], melody_floor)
            # The bar boundary in beats: no accompaniment note may sound past
            # here, so the previous chord always stops before the next chord.
            for pitch, ev_start, ev_dur, vel in style_fn(
                pitches, start_beat, dur_beats, velocity
            ):
                # Clamp the note so it never bleeds into the next chord's bar.
                ev_end = min(ev_start + ev_dur, bar_end_beat)
                if ev_end <= ev_start:
                    continue  # fully out of bounds; skip
                # Equal, loud volume: force a fixed velocity if configured,
                # otherwise keep the style's own dynamics (scaled).
                if ACCOMP_FIXED_VELOCITY is not None:
                    scaled_vel = ACCOMP_FIXED_VELOCITY
                else:
                    scaled_vel = max(1, min(127, int(vel * ACCOMP_VELOCITY_SCALE)))
                note_start = ev_start * spb
                note_end = _trim_for_release(note_start, ev_end * spb)
                acc.notes.append(
                    pretty_midi.Note(
                        velocity=scaled_vel,
                        pitch=_not_too_low(int(pitch)),
                        start=note_start,
                        end=note_end,
                    )
                )
        else:
            pitches = _pitches_below_melody(chord_pitches(chord, octave), melody_floor)
            if style == "block":
                _add_block(acc, pitches, start_beat, dur_beats, spb, velocity)
            else:  # "broken"
                _add_broken(acc, pitches, start_beat, dur_beats, spb, velocity)

    for note in acc.notes:  # block/broken paths too
        note.pitch = _not_too_low(note.pitch)
    _set_channel_volume(acc, ACCOMP_CHANNEL_VOLUME)
    pm.instruments.append(acc)

    if melody_notes:
        # Melody on its own track, played loud so it clearly leads.
        mel = pretty_midi.Instrument(program=melody_program)
        _set_channel_volume(mel, MELODY_CHANNEL_VOLUME)
        for n in melody_notes:
            start = n["start"] * spb
            end = start + n["duration"] * spb
            mel.notes.append(
                pretty_midi.Note(
                    velocity=MELODY_VELOCITY,
                    pitch=int(n["pitch"]),
                    start=start,
                    end=end,
                )
            )
        pm.instruments.append(mel)

    pm.write(path)
    return path


def _not_too_low(pitch: int) -> int:
    """Raise a note by octaves until it's at or above LOWEST_ACCOMPANIMENT_NOTE."""
    while pitch < LOWEST_ACCOMPANIMENT_NOTE:
        pitch += 12
    return pitch


def _set_channel_volume(inst, volume: int) -> None:
    """MIDI channel volume (CC7) at the start of the track."""
    inst.control_changes.append(
        pretty_midi.ControlChange(number=7, value=int(volume), time=0.0)
    )


def _add_block(inst, pitches, start_beat, dur_beats, spb, velocity):
    start = start_beat * spb
    end = _trim_for_release(start, (start_beat + dur_beats) * spb)
    for p in pitches:
        inst.notes.append(
            pretty_midi.Note(velocity=velocity, pitch=p, start=start, end=end)
        )


def _add_broken(inst, pitches, start_beat, dur_beats, spb, velocity):
    """Broken-chord pattern: root, fifth, third, fifth across the bar."""
    steps = len(BROKEN_PATTERN)
    step_beats = dur_beats / steps
    for k, idx in enumerate(BROKEN_PATTERN):
        # idx points into [root, third, fifth]; clamp for non-triads.
        pitch = pitches[idx % len(pitches)]
        note_start = (start_beat + k * step_beats) * spb
        note_end = _trim_for_release(note_start, note_start + step_beats * spb)
        inst.notes.append(
            pretty_midi.Note(
                velocity=velocity, pitch=pitch, start=note_start, end=note_end
            )
        )
