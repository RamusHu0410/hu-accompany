"""Makes the song from the user's own hum, with the song settings translated for the engine.

The accompanist engine writes the song: its tune and accompaniment tracks, in its own style,
voicing and instrument (the lead, synth by default), are kept exactly as it renders them.
Talk mode only adds on top (background parts, the lead's level, energy).

The hum is the WAV that POST /upload saved. analyze_audio_file turns it into notes (MIDI pitch,
start and length in seconds) plus a tempo; hum.engine.audio.handoff turns those into beats on a
sixteenth-note grid, the way the accompanist engine counts. This file adds the song settings:

    speed        0 → 1   tempo from half to one and a half times the hum's (0.5 keeps it as hummed)
    pitch        0 → 1   the tune moves down or up to an octave (0.5 keeps it as hummed)
    emotion      0 → 1   below 0.4 minor, above 0.6 major, in between the hum's own mode
    style                a genre word from talk mode, mapped to one of the engine's styles
    instruments          the lead plays the engine's tune and chords; every other instrument gets a
                         track of its own underneath: held chords, a bass line, or a drum beat
    energy               the first or the second half played calmer or bigger

The engine writes the same notes for the same hum and settings (its jazz feel is random, so it
gets the same seed every time). So adding an instrument leaves the others exactly as they were:
it is one more MIDI track, not a new song. The instruments come from the soundfont FluidSynth
uses (ECKO_SOUNDFONT in backend/.env). FluidSynth renders very quietly, so the finished song is
brought up to a normal volume.
"""

import io
import os
import random
import tempfile
import threading
from functools import lru_cache

import numpy as np
import pretty_midi
import soundfile
from hum.engine.accompanist.audio.render import render_midi
from hum.engine.accompanist.generate import generate_accompaniment
from hum.engine.accompanist.music.chord_to_midi import chord_pitches

from ..audio.handoff import seconds_from_engine, sensible_tempo, to_engine_melody
from ..audio.processor import analyze_audio_file
from .settings import DEFAULT_LEAD, DRUMS, SongSettings, clean_label

ENGINE_STYLE_FOR = {
    "pop": "pop",
    "rock": "pop",
    "dance": "pop",
    "jazz": "jazz",
    "swing": "jazz",
    "blues": "jazz",
    "piano": "piano",
    "lullaby": "piano",
    "lo-fi": "piano",
    "ballad": "piano",
    "classical": "classical",
    "cinematic": "cinematic",
    "orchestral": "cinematic",
    "epic": "cinematic",
    "folk": "asian_folk",
    "asian folk": "asian_folk",
}
UNKNOWN_STYLE = "pop"  # a genre the engine doesn't know still gets a lively backing

PROGRAMS = {  # the instruments ECKO can play, as General MIDI program numbers (every soundfont uses them)
    "piano": 0,
    "electric piano": 4,
    "harpsichord": 6,
    "celesta": 8,
    "glockenspiel": 9,
    "music box": 10,
    "vibraphone": 11,
    "marimba": 12,
    "xylophone": 13,
    "organ": 19,
    "accordion": 21,
    "harmonica": 22,
    "guitar": 24,
    "acoustic guitar": 25,
    "jazz guitar": 26,
    "electric guitar": 27,
    "bass": 33,
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "double bass": 43,
    "harp": 46,
    "strings": 48,
    "choir": 52,
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "french horn": 60,
    "brass": 61,
    "sax": 66,
    "oboe": 68,
    "bassoon": 70,
    "clarinet": 71,
    "flute": 73,
    "recorder": 74,
    "synth": 81,
    "synth pad": 89,
    "sitar": 104,
    "banjo": 105,
    DRUMS: 0,  # drums play on the drum channel, where the program number doesn't matter
}
OTHER_NAMES = {
    "grand piano": "piano",
    "keys": "electric piano",
    "bells": "glockenspiel",
    "ukulele": "guitar",
    "bass guitar": "bass",
    "upright bass": "double bass",
    "contrabass": "double bass",
    "string section": "strings",
    "voices": "choir",
    "horn": "french horn",
    "saxophone": "sax",
    "alto sax": "sax",
    "tenor sax": "sax",
    "pad": "synth pad",
    "drum": DRUMS,
    "drum kit": DRUMS,
    "percussion": DRUMS,
    "beat": DRUMS,
}
LOW = {"bass", "cello", "double bass", "trombone", "tuba", "bassoon"}  # these play a bass line instead of chords

# MIDI channel volume by level. 100 is FluidSynth's own default, so an unchanged lead sounds as before.
# Measured with the app's soundfont: a soft background part is about a fifth as loud as the lead,
# and even a loud one stays under a normal lead.
LEAD_VOLUME = {"soft": 70, "normal": 100, "loud": 127}
BACKGROUND_VOLUME = {"soft": 50, "normal": 70, "loud": 90}
CHORD_VELOCITY, BASS_VELOCITY = 80, 100
BEAT = ((36, 100, (0, 4)), (38, 90, (2, 6)), (42, 60, range(8)))  # kick on beats 1 and 3, snare on 2 and 4, hi-hat on every eighth
HIT_SECONDS = 0.1
RELEASE_SECONDS = 0.03  # a held chord ends this much early, so the next one doesn't cut its ring short
ENERGY_STEP = 0.2  # each step of energy plays that half's notes this much harder or softer

PEAK_LEVEL = 0.9  # the loudest moment of the song, where 1.0 is full scale
OCTAVE = 12
_SEEDING = threading.Lock()  # random.seed is shared by the whole server


def make_song(hum_path: str, settings: SongSettings) -> bytes:
    """The song as WAV bytes. Raises ValueError if the hum has no tune (or isn't a usable
    recording: AudioInputError is a ValueError), SongError if it can't be heard."""
    analysis = _analyze(hum_path, os.stat(hum_path).st_mtime_ns)
    if not analysis["melody"]:
        raise ValueError("No tune was found in that hum. Try humming a little louder.")
    with tempfile.TemporaryDirectory() as folder:
        midi_path, wav_path = os.path.join(folder, "song.mid"), os.path.join(folder, "song.wav")
        write_midi(midi_path, analysis, settings, seed=hum_path)
        try:
            render_midi(midi_path, wav_path)
        except Exception as exc:  # usually FluidSynth or its soundfont is missing
            raise SongError(f"The song couldn't be turned into audio: {exc}") from exc
        return _at_normal_volume(wav_path)


def write_midi(midi_path: str, analysis: dict, settings: SongSettings, seed: str) -> None:
    """The song as MIDI: the engine's tune and chords, then a track for each other instrument."""
    request = engine_request(analysis, settings)
    melody = {"melody": request.pop("melody"), "tempo": request["tempo"]}
    with _SEEDING:
        random.seed(seed)  # the jazz style's feel is random; the same seed keeps it the same in every version
        result = generate_accompaniment(melody, midi_path, **request)
    arrange(midi_path, result.progression, settings, request["tempo"])


def engine_request(analysis: dict, settings: SongSettings) -> dict:
    """The generate_accompaniment arguments for this hum with these settings."""
    hum_tempo = sensible_tempo(analysis.get("tempo"))
    shift = round((settings.pitch - 0.5) * 2 * OCTAVE)
    request = {
        # the engine's "hz" holds MIDI note numbers; the rhythm is counted at the hum's own tempo
        "melody": to_engine_melody(analysis["melody"], hum_tempo, shift=shift),
        "tempo": round(hum_tempo * (0.5 + settings.speed), 1),
        # the engine renders its own tracks with the lead's instrument; nothing re-dresses them later
        "instrument": PROGRAMS.get(_lead(settings).name, PROGRAMS["synth"]),
    }
    if settings.style:
        request["style"] = ENGINE_STYLE_FOR.get(settings.style, UNKNOWN_STYLE)
    if settings.emotion < 0.4:
        request["mode"] = "minor"
    elif settings.emotion > 0.6:
        request["mode"] = "major"
    return request


def _lead(settings: SongSettings):
    return next((part for part in settings.instruments if part.role == "lead"), DEFAULT_LEAD)


def arrange(midi_path: str, chords: list, settings: SongSettings, tempo: float) -> None:
    """Keeps the engine's own tracks (tune and accompaniment) exactly as it wrote them, notes and
    instruments alike, and adds the talk-mode extras on top: the lead's level, a track for every
    background instrument (only in its section), and the energy of each half. At the default
    settings every extra is a no-op, so the song is the accompanist's output."""
    song = pretty_midi.PrettyMIDI(midi_path)
    lead = _lead(settings)
    for track in song.instruments:
        _scale_volume(track, LEAD_VOLUME[lead.level] / LEAD_VOLUME["normal"])  # normal = unchanged
    half = song.get_end_time() / 2
    seconds_per_beat = 60 / tempo
    for part in settings.instruments:
        if part.role == "background" and part.name in PROGRAMS:
            track = _beat(chords, seconds_per_beat, half * 2) if part.name == DRUMS else _held_chords(part.name, chords, seconds_per_beat)
            track.notes = [note for note in track.notes if _plays(part.section, note.start, half)]
            _set_volume(track, BACKGROUND_VOLUME[part.level])
            song.instruments.append(track)
    for track in song.instruments:
        for note in track.notes:
            steps = settings.energy[0] if note.start < half else settings.energy[1]
            note.velocity = max(1, min(127, round(note.velocity * (1 + ENERGY_STEP * steps))))
    song.write(midi_path)


def instrument_name(word) -> str | None:
    """The name ECKO uses for an instrument ('violins' → 'violin', 'saxophone' → 'sax'), or None if it has no sound for it."""
    label = clean_label(word) or ""
    for name in (label, label[:-1] if label.endswith("s") else label):
        name = OTHER_NAMES.get(name, name)
        if name in PROGRAMS:
            return name
    return None


def song_notes(hum_path: str, settings: SongSettings) -> dict:
    """For the notes graph: the notes heard in the hum, and the ones the song's tune plays."""
    return notes_from(_analyze(hum_path, os.stat(hum_path).st_mtime_ns), settings)


def notes_from(analysis: dict, settings: SongSettings) -> dict:
    """Both lists as MIDI pitch with start and length in seconds, so they share one time axis
    (the song's first note is placed where the hum's first note was), plus the hum's pitch as it
    was actually sung (``contour``), which is what the graph draws the line from."""
    request = engine_request(analysis, settings)
    first = min((n["start"] for n in analysis["melody"]), default=0.0)
    return {
        "sung": [_note(n["hz"], n["start"], n["duration"]) for n in analysis["melody"]],
        "played": [_note(n["hz"], n["start"], n["duration"]) for n in seconds_from_engine(request["melody"], request["tempo"], first)],
        "contour": analysis.get("contour", {"step": 0.0, "segments": []}),
    }


class SongError(Exception):
    """The engine made the song but couldn't render it to audio (usually FluidSynth is missing)."""


def _held_chords(name: str, chords: list, seconds_per_beat: float) -> pretty_midi.Instrument:
    """Each chord held for as long as it lasts. A low instrument holds just the chord's root, as a bass line."""
    track = pretty_midi.Instrument(program=PROGRAMS[name], name=name)
    for chord in chords:
        start = chord.start * seconds_per_beat
        end = (chord.start + chord.duration) * seconds_per_beat - RELEASE_SECONDS
        pitches = chord_pitches(chord, octave=2)[:1] if name in LOW else chord_pitches(chord, octave=4)
        velocity = BASS_VELOCITY if name in LOW else CHORD_VELOCITY
        track.notes += [pretty_midi.Note(velocity=velocity, pitch=pitch, start=start, end=end) for pitch in pitches]
    return track


def _beat(chords: list, seconds_per_beat: float, song_seconds: float) -> pretty_midi.Instrument:
    """A simple beat in eighth notes, for as long as the chords last (or the whole song, when the
    engine found no chords for the hum)."""
    track = pretty_midi.Instrument(program=0, is_drum=True, name=DRUMS)
    beats = max((chord.start + chord.duration for chord in chords), default=song_seconds / seconds_per_beat)
    for eighth in range(int(beats * 2)):
        at = eighth / 2 * seconds_per_beat
        for drum, velocity, eighths in BEAT:
            if eighth % 8 in eighths:
                track.notes.append(pretty_midi.Note(velocity=velocity, pitch=drum, start=at, end=at + HIT_SECONDS))
    return track


def _plays(section: str, at: float, half: float) -> bool:
    if section == "start":
        return at < half
    if section == "end":
        return at >= half
    return True


def _set_volume(track: pretty_midi.Instrument, volume: int) -> None:
    track.control_changes.append(pretty_midi.ControlChange(number=7, value=volume, time=0.0))  # 7 = channel volume


def _scale_volume(track: pretty_midi.Instrument, factor: float) -> None:
    """Scale the channel volume the engine set (keeps its melody/accompaniment balance)."""
    current = [change for change in track.control_changes if change.number == 7]
    base = current[0].value if current else 100
    track.control_changes = [change for change in track.control_changes if change.number != 7]
    _set_volume(track, max(0, min(127, round(base * factor))))


def _note(midi: float, start: float, duration: float) -> dict:
    return {"midi": round(midi, 2), "start": round(start, 3), "duration": round(duration, 3)}


def _at_normal_volume(wav_path: str) -> bytes:
    samples, rate = soundfile.read(wav_path)
    peak = np.abs(samples).max()
    if peak > 0:
        samples = samples * (PEAK_LEVEL / peak)
    wav = io.BytesIO()
    soundfile.write(wav, samples, rate, format="WAV", subtype="PCM_16")
    return wav.getvalue()


@lru_cache(maxsize=4)
def _analyze(hum_path: str, _changed_at: int) -> dict:
    """The hum's notes and tempo. Remakes reuse it; a new hum (a new change time) is analysed again."""
    return analyze_audio_file(hum_path)
