"""Full accompaniment generation pipeline (Phase 18 — the MVP engine).

Chains every stage:

    JSON -> Melody -> Key -> Segments -> Chord candidates -> Scoring ->
    Progression optimization -> Voice leading -> Style pattern -> MIDI -> WAV
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.models.melody import Melody
from hum.engine.accompanist.music.key_detection import detect_key_from_notes
from hum.engine.accompanist.music.progression import generate_progression
from hum.engine.accompanist.music.accompaniment import render_accompaniment, INSTRUMENTS
from hum.engine.accompanist.music.styles import STYLES, STYLE_SCALES
from hum.engine.accompanist.music.scales import snap_notes

DEFAULT_BEATS_PER_BAR = 4.0

# Debug bypass: while enabled, generate_accompaniment skips key detection,
# modulation, melody editing, harmony, progression, voice leading, and style
# generation. The output MIDI/WAV contains only the untouched input melody.
DEBUG_BYPASS_GENERATION = False


@dataclass
class AccompanimentResult:
    """The output of a generation run."""

    key: str
    mode: str
    melody_notes: list[dict]
    progression: list[Chord]
    midi_path: str
    wav_path: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def progression_symbols(self) -> list[str]:
        return [c.symbol for c in self.progression]


def _melody_from_input(data) -> Melody:
    """Accept a JSON string, a dict, or a Melody and return a Melody."""
    if isinstance(data, Melody):
        return data
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        return Melody.from_dict(data)
    raise TypeError(f"Unsupported melody input type: {type(data).__name__}")


def _melody_to_note_dicts(melody: Melody) -> list[dict]:
    """Convert a Melody's notes into pitch/start/duration dicts (in beats).

    The Melody stores time in the same units it was given (Kingsley's JSON uses
    beats), and `hz` actually holds MIDI pitch numbers throughout this project.
    """
    return [
        {
            "pitch": int(round(n.hz)),
            "start": float(n.start),
            "duration": float(n.duration),
        }
        for n in melody.notes
    ]


def _resolve_program(instrument, warnings: list[str]) -> int:
    """GM program for `instrument`: a name from INSTRUMENTS, or a GM number 0-127.

    Unknown names fall back to the default synth (with a warning).
    """
    if isinstance(instrument, int) and not isinstance(instrument, bool):
        if 0 <= instrument <= 127:
            return instrument
        warnings.append(f"GM program {instrument} is out of range; defaulting to synth.")
        return INSTRUMENTS["synth"]
    if instrument in INSTRUMENTS:
        return INSTRUMENTS[instrument]
    warnings.append(
        f"Unknown instrument '{instrument}'; defaulting to synth. "
        f"Options: {sorted(INSTRUMENTS)}"
    )
    return INSTRUMENTS["synth"]


def generate_accompaniment(
    melody_input,
    midi_path: str = "accompaniment.mid",
    *,
    style: str = "classical",
    key: Optional[str] = None,
    mode: Optional[str] = None,
    tempo: Optional[float] = None,
    beats_per_bar: float = DEFAULT_BEATS_PER_BAR,
    include_melody: bool = True,
    allow_edit_melody: bool = False,
    instrument: str | int = "synth",
    modulate_to_key: Optional[str] = None,
    modulate_to_mode: Optional[str] = None,
    render_wav: bool = False,
    wav_path: Optional[str] = None,
):
    """Generate an accompaniment for a melody, end to end.

    When DEBUG_BYPASS_GENERATION is True, all composition stages are skipped
    and the output contains only the original, untouched melody.

    Args:
        melody_input: A JSON string, a melody dict (Kingsley's format), or a
            Melody object.
        midi_path: Where to write the accompaniment MIDI.
        style: Accompaniment style ("piano", "pop", "cinematic", "classical").
        key: Override the detected key tonic (e.g. "C"). Auto-detected if None.
        mode: Override the detected mode ("major"/"minor"). Auto if None.
        tempo: Override tempo (BPM). Falls back to the melody's tempo.
        beats_per_bar: Bar length in beats.
        include_melody: Also write the melody on its own track. Debug bypass
            ignores this option and always writes the original melody.
        allow_edit_melody: If True, the engine may modify the melody itself —
            snapping pitches to the style's scale and (for jazz) applying a
            swung, ornamented feel. If False (default), the melody is left
            exactly as given and only the accompaniment reflects the style.
        instrument: Named instrument for playback, e.g. "synth", "synth_pad",
            "piano", "guitar", "guitar_jazz", "strings", "sax". Applies to
            both tracks; defaults to "synth". A General MIDI program number
            (0-127) is also accepted.
        modulate_to_key: Transpose the whole piece to this tonic (e.g. "G").
            The melody is shifted and the harmony re-derived in the new key.
        modulate_to_mode: Switch to this mode ("major"/"minor"). Combined with
            modulate_to_key, e.g. C major -> A minor.
        render_wav: If True, also render a WAV via FluidSynth.
        wav_path: WAV output path (defaults to midi_path with .wav).

    Returns:
        An AccompanimentResult describing what was produced.
    """
    warnings: list[str] = []

    # 1. JSON -> Melody. Keep this before the debug bypass so malformed or
    # empty input still receives a useful error.
    melody = _melody_from_input(melody_input)
    melody_notes = _melody_to_note_dicts(melody)
    if not melody_notes:
        raise ValueError("Melody has no notes.")

    if DEBUG_BYPASS_GENERATION:
        resolved_tempo = tempo or float(melody.tempo)
        resolved_key = key or melody.key
        resolved_mode = mode or melody.mode
        warnings.append(
            "DEBUG_BYPASS_GENERATION is enabled: all composition stages were "
            "skipped and only the original melody was rendered."
        )
        program = _resolve_program(instrument, warnings)

        # An empty chord list means there is no accompaniment track content;
        # the untouched input melody is the only audible material.
        render_accompaniment(
            [],
            midi_path,
            style="block",
            tempo=resolved_tempo,
            beats_per_bar=beats_per_bar,
            program=program,
            melody_program=program,
            melody_notes=melody_notes,
        )

        out_wav = None
        if render_wav:
            out_wav = wav_path or (midi_path.rsplit(".", 1)[0] + ".wav")
            try:
                from hum.engine.accompanist.audio.render import render_midi

                render_midi(midi_path, out_wav)
            except Exception as exc:
                warnings.append(f"WAV rendering skipped: {exc}")
                out_wav = None

        return AccompanimentResult(
            key=resolved_key,
            mode=resolved_mode,
            melody_notes=melody_notes,
            progression=[],
            midi_path=midi_path,
            wav_path=out_wav,
            warnings=warnings,
        )

    if style not in STYLES:
        raise ValueError(f"Unknown style '{style}'. Choose from: {sorted(STYLES)}")

    # 2. Key detection (respect overrides / melody metadata; else auto-detect).
    resolved_key = key
    resolved_mode = mode
    if resolved_key is None or resolved_mode is None:
        detected = detect_key_from_notes(melody_notes)
        resolved_key = resolved_key or detected.tonic.name.replace("-", "b")
        resolved_mode = resolved_mode or detected.mode

    resolved_tempo = tempo or float(melody.tempo)

    # 2a. Modulation: transpose the piece into a different key/mode if asked.
    if modulate_to_key is not None or modulate_to_mode is not None:
        from hum.engine.accompanist.music.modulation import resolve_target, modulate_notes

        dest_key, dest_mode, shift = resolve_target(
            resolved_key, resolved_mode, modulate_to_key, modulate_to_mode
        )
        if shift != 0:
            melody_notes = modulate_notes(melody_notes, resolved_key, dest_key)
        warnings.append(
            f"Modulated from {resolved_key} {resolved_mode} to "
            f"{dest_key} {dest_mode} (transposed {shift:+d} semitones)."
        )
        resolved_key, resolved_mode = dest_key, dest_mode

    # 2b. Scale flavoring + melody editing.
    #     Harmony is always derived from scale-correct notes for scale-based
    #     styles, but the *melody track* is only modified when the caller opts
    #     in via allow_edit_melody.
    scale_name = STYLE_SCALES.get(style)
    harmony_notes = melody_notes  # what the chord selection reasons over

    if scale_name is not None:
        # Snap the harmony source so chords fit the style's scale regardless.
        harmony_notes = snap_notes(melody_notes, resolved_key, scale_name)

        if allow_edit_melody:
            if style == "jazz":
                # Full jazz treatment: snap + swing feel + light ornamentation.
                from hum.engine.accompanist.music.melody_styling import jazz_stylize

                melody_notes = jazz_stylize(melody_notes, resolved_key, scale_name)
                warnings.append(
                    "Melody edited: snapped to the jazz scale and given a "
                    "swung, ornamented jazz feel."
                )
            else:
                melody_notes = snap_notes(melody_notes, resolved_key, scale_name)
                warnings.append(
                    f"Melody edited: snapped to the {scale_name} scale for "
                    f"'{style}' style."
                )
        else:
            warnings.append(
                "Melody left unedited (allow_edit_melody is off); only the "
                "accompaniment reflects the style."
            )

    # 3-7. Segments -> candidates -> scoring -> progression optimization.
    #      (voice leading is applied inside render for the classical style)
    progression = generate_progression(
        harmony_notes,
        key=resolved_key,
        mode=resolved_mode,
        beats_per_bar=beats_per_bar,
    )

    # 8-9. Style pattern -> MIDI (with the chosen instrument on both tracks)
    program = _resolve_program(instrument, warnings)
    render_accompaniment(
        progression,
        midi_path,
        style=style,
        tempo=resolved_tempo,
        beats_per_bar=beats_per_bar,
        program=program,
        melody_program=program,
        melody_notes=melody_notes if include_melody else None,
    )

    # 10. MIDI -> WAV (optional; requires FluidSynth + soundfont)
    out_wav = None
    if render_wav:
        out_wav = wav_path or (midi_path.rsplit(".", 1)[0] + ".wav")
        try:
            from hum.engine.accompanist.audio.render import render_midi

            render_midi(midi_path, out_wav)
        except Exception as exc:  # FluidSynth/soundfont not available
            warnings.append(f"WAV rendering skipped: {exc}")
            out_wav = None

    res = AccompanimentResult(
        key=resolved_key,
        mode=resolved_mode,
        melody_notes=melody_notes,
        progression=progression,
        midi_path=midi_path,
        wav_path=out_wav,
        warnings=warnings,
    )
    return res
