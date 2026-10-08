"""Plays a hum back as it was hummed, and exports it as MIDI.

Takes the transcription's raw notes: exact onsets and durations, no quantizing, no scale snapping,
no accompaniment. The only change is that pitches are whole MIDI notes, because that is all a
keyboard or a MIDI file can say (the transcriber has already taken out how flat or sharp the whole
hum was). Kept apart from the views so the app, the tests and a future Studio use the same code.
"""

import io
import os
import tempfile

import numpy as np
import pretty_midi
import soundfile

from hum.engine.accompanist.audio.render import render_midi
from hum.transcription import HeardNote, Transcription

# General MIDI programs: an acoustic grand piano, and a soft square-wave lead as the plain synth.
INSTRUMENTS = {"piano": 0, "synth": 80}
DEFAULT_INSTRUMENT = "piano"
TAIL_SECONDS = 0.8  # room after the last note for it to ring out
PEAK = 0.9  # FluidSynth renders quietly; bring the hum up to a normal level
SILENCE = 0.001  # -60 dBFS: quieter than this at the end is silence FluidSynth padded on


class RenderUnavailable(RuntimeError):
    """FluidSynth or a soundfont isn't on this machine."""


def midi_for(notes: list[HeardNote], tempo_bpm: float, program: int = 0, name: str = "Hum") -> pretty_midi.PrettyMIDI:
    midi = pretty_midi.PrettyMIDI(initial_tempo=float(tempo_bpm))
    track = pretty_midi.Instrument(program=program, name=name)
    for note in notes:
        track.notes.append(
            pretty_midi.Note(velocity=int(note.velocity), pitch=int(note.pitch), start=note.start, end=note.end)
        )
    midi.instruments.append(track)
    return midi


def export_midi(transcription: Transcription) -> bytes:
    """The raw transcription as a standard MIDI file: one piano track at the hum's tempo, notes
    exactly where they were hummed."""
    buffer = io.BytesIO()
    midi_for(transcription.raw, transcription.tempo_bpm).write(buffer)
    return buffer.getvalue()


def render_raw(transcription: Transcription, instrument: str = DEFAULT_INSTRUMENT) -> bytes:
    """The raw notes as a 16-bit WAV, played on "piano" or "synth". Raises ValueError for any other
    instrument and RenderUnavailable when there is nothing to render with."""
    if instrument not in INSTRUMENTS:
        raise ValueError(f"instrument must be one of {', '.join(INSTRUMENTS)}.")
    midi = midi_for(transcription.raw, transcription.tempo_bpm, INSTRUMENTS[instrument])
    # A control change after the last note keeps the file (and so the render) going while it rings out.
    midi.instruments[0].control_changes.append(
        pretty_midi.ControlChange(number=64, value=0, time=transcription.duration + TAIL_SECONDS)
    )
    with tempfile.TemporaryDirectory(prefix="hum-raw-") as scratch:
        midi_path = os.path.join(scratch, "hum.mid")
        wav_path = os.path.join(scratch, "hum.wav")
        midi.write(midi_path)
        try:
            render_midi(midi_path, wav_path)
        except (FileNotFoundError, RuntimeError) as exc:
            raise RenderUnavailable(str(exc)) from exc
        samples, rate = soundfile.read(wav_path)
        loudest = np.abs(samples).max()
        if loudest > 0:
            samples = samples * (PEAK / loudest)
        samples = without_trailing_silence(samples, rate)
        out = io.BytesIO()
        soundfile.write(out, samples, rate, format="WAV", subtype="PCM_16")
        return out.getvalue()


def without_trailing_silence(samples: np.ndarray, rate: int, keep_seconds: float = 0.05) -> np.ndarray:
    """FluidSynth keeps writing silence for a couple of seconds after the last sound; cut it, so the
    player says "finished" when the music does."""
    level = np.abs(samples) if samples.ndim == 1 else np.abs(samples).max(axis=1)
    sounding = np.flatnonzero(level > SILENCE)
    if len(sounding) == 0:
        return samples
    return samples[: min(len(samples), sounding[-1] + 1 + int(keep_seconds * rate))]
