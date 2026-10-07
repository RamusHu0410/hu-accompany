"""The handoff melody (melody.json, see the pipeline contract) and its music21 form.

melody.json is the source of truth for key and tempo. Times are in beats (quarter notes).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import pretty_midi
from music21 import key as m21key
from music21 import meter, note, stream, tempo

from .files import write_atomically
from .validate import validate_midi


@dataclass(frozen=True)
class Note:
    pitch: int
    start_beats: float
    duration_beats: float
    velocity: int = 80

    @property
    def end_beats(self) -> float:
        return self.start_beats + self.duration_beats


@dataclass(frozen=True)
class Melody:
    tempo_bpm: float
    key: str
    time_signature: str
    tuning_offset_cents: float
    notes: tuple[Note, ...] = field(default_factory=tuple)
    # Bars (0-based) where a new section starts, e.g. where the tune begins after an introduction
    # the transformations added. Not part of the contract's melody.json; only written when set.
    sections: tuple[int, ...] = ()
    # The piece's length in bars when it runs on after its last note (an ending that lets the final
    # chord ring). Not part of the contract's melody.json either; only written when set.
    length_bars: int | None = None

    @property
    def beats_per_bar(self) -> float:
        return beats_per_bar(self.time_signature)

    @property
    def end_beats(self) -> float:
        return max((n.end_beats for n in self.notes), default=0.0)

    @property
    def bars(self) -> int:
        return max(1, math.ceil(self.end_beats / self.beats_per_bar - 1e-9), self.length_bars or 0)

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.tempo_bpm

    def with_notes(self, notes) -> Melody:
        return replace(self, notes=tuple(notes))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["notes"] = [asdict(n) for n in self.notes]
        if self.sections:
            data["sections"] = list(self.sections)
        else:
            del data["sections"]
        if self.length_bars is None:
            del data["length_bars"]
        return data


# --- key and meter ---------------------------------------------------------------------------

_KEY_NAME = re.compile(r"^\s*([A-Ga-g])([#b\-]*)\s+(major|minor)\s*$", re.IGNORECASE)


def parse_key(name: str) -> m21key.Key:
    """"D minor", "Bb major", "B- major" (music21's flat), "F# minor" -> a music21 Key."""
    match = _KEY_NAME.match(name or "")
    if not match:
        raise ValueError(f"Unrecognised key {name!r}; expected e.g. 'D minor' or 'B- major'.")
    letter, accidentals, mode = match.groups()
    tonic = letter.upper() + accidentals.replace("b", "-")
    return m21key.Key(tonic, mode.lower())


def key_tonic_and_mode(name: str) -> tuple[str, str]:
    """("Bb", "major") style names for code that doesn't speak music21 (the accompanist)."""
    k = parse_key(name)
    return k.tonic.name.replace("-", "b"), k.mode


def key_pitch_classes(name: str) -> set[int]:
    """The key's scale (natural minor for minor keys)."""
    return {p.pitchClass for p in parse_key(name).getScale().getPitches("C1", "C2")}


def scale_pitch_classes(name: str) -> list[int]:
    """The key's seven scale degrees from the tonic (natural minor for minor keys).

    music21 lists a minor scale from its relative major (F G A Bb C D E for D minor), so it's
    rotated to start on the tonic."""
    k = parse_key(name)
    scale = [p.pitchClass for p in k.getScale().getPitches()[:7]]
    start = scale.index(k.tonic.pitchClass)
    return scale[start:] + scale[:start]


# How each key is usually spelled (the fewest sharps or flats), by tonic pitch class.
_MAJOR_TONICS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_MINOR_TONICS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]


def key_name(tonic_pitch_class: int, mode: str) -> str:
    """(2, "minor") -> "D minor"."""
    return f"{(_MAJOR_TONICS if mode == 'major' else _MINOR_TONICS)[tonic_pitch_class % 12]} {mode}"


def beats_per_bar(time_signature: str) -> float:
    """"4/4" -> 4.0, "6/8" -> 3.0 (in quarter notes)."""
    try:
        numerator, denominator = (int(part) for part in time_signature.split("/"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Unrecognised time signature {time_signature!r}.") from exc
    if numerator <= 0 or denominator not in (1, 2, 4, 8, 16, 32):
        raise ValueError(f"Unrecognised time signature {time_signature!r}.")
    return numerator * 4.0 / denominator


# --- melody.json ------------------------------------------------------------------------------

# Beats within a hair of this grid are taken as exactly on it (1/48 beat covers 16ths, 32nds and
# triplets), so a triplet written with six decimals (0.333333) is a third of a beat again.
GRID = 48
_GRID_TOLERANCE = 1e-3


def _on_grid(beats: float) -> float:
    snapped = round(beats * GRID) / GRID
    return snapped if abs(beats - snapped) < _GRID_TOLERANCE else beats



def melody_from_dict(data: dict) -> Melody:
    """Validate the contract's JSON and build a Melody. Raises ValueError on anything off."""
    try:
        tempo_bpm = float(data["tempo_bpm"])
        key_name = str(data["key"])
        time_signature = str(data.get("time_signature", "4/4"))
        tuning = float(data.get("tuning_offset_cents", 0))
        raw_notes = data["notes"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"melody.json is missing or has a bad field: {exc}") from exc
    if not 20 <= tempo_bpm <= 300:
        raise ValueError(f"tempo_bpm {tempo_bpm} is outside 20-300.")
    parse_key(key_name)
    beats_per_bar(time_signature)
    if not raw_notes:
        raise ValueError("melody.json has no notes.")

    notes = []
    for i, raw in enumerate(raw_notes):
        try:
            n = Note(
                pitch=int(raw["pitch"]),
                start_beats=_on_grid(float(raw["start_beats"])),
                duration_beats=_on_grid(float(raw["duration_beats"])),
                velocity=int(raw.get("velocity", 80)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Note {i} is malformed: {exc}") from exc
        if not 0 <= n.pitch <= 127 or not 1 <= n.velocity <= 127:
            raise ValueError(f"Note {i} has pitch/velocity out of MIDI range: {raw}.")
        if n.start_beats < 0 or n.duration_beats <= 0 or not math.isfinite(n.end_beats):
            raise ValueError(f"Note {i} has a bad start/duration: {raw}.")
        notes.append(n)
    notes.sort(key=lambda n: (n.start_beats, n.pitch))
    try:
        sections = tuple(sorted({int(bar) for bar in data.get("sections", ()) if int(bar) >= 0}))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'sections' must be a list of bar numbers: {exc}") from exc
    length = data.get("length_bars")
    if length is not None and (not isinstance(length, int) or length < 1):
        raise ValueError("'length_bars' must be a whole number of bars.")
    return Melody(tempo_bpm, key_name, time_signature, tuning, tuple(notes), sections, length)


def load_melody(path: str | Path) -> Melody:
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} isn't valid JSON: {exc}") from exc
    return melody_from_dict(data)


def save_melody_json(melody: Melody, path: str | Path) -> Path:
    def write(tmp: Path) -> None:
        tmp.write_text(json.dumps(melody.to_dict(), indent=2) + "\n", encoding="utf-8")

    return write_atomically(path, write, validate=load_melody)


def empty_midi(melody: Melody) -> pretty_midi.PrettyMIDI:
    """A MIDI file with the melody's tempo, meter and key, and no tracks yet."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=melody.tempo_bpm)
    numerator, denominator = (int(p) for p in melody.time_signature.split("/"))
    midi.time_signature_changes.append(pretty_midi.TimeSignature(numerator, denominator, 0.0))
    tonic, mode = key_tonic_and_mode(melody.key)
    midi.key_signature_changes.append(
        pretty_midi.KeySignature(pretty_midi.key_name_to_key_number(f"{tonic} {mode}"), 0.0)
    )
    return midi


def melody_to_midi(melody: Melody, program: int = 0, name: str = "melody") -> pretty_midi.PrettyMIDI:
    """A single-track MIDI of the melody, with its tempo, meter and key."""
    midi = empty_midi(melody)
    track = pretty_midi.Instrument(program=program, name=name)
    spb = melody.seconds_per_beat
    for n in melody.notes:
        track.notes.append(pretty_midi.Note(n.velocity, n.pitch, n.start_beats * spb, n.end_beats * spb))
    midi.instruments.append(track)
    return midi


def save_melody_midi(melody: Melody, path: str | Path, program: int = 0) -> Path:
    return write_atomically(path, lambda tmp: melody_to_midi(melody, program).write(str(tmp)), validate_midi)


# --- music21 ----------------------------------------------------------------------------------


def to_stream(melody: Melody) -> stream.Part:
    """A music21 Part: the notes at their offsets, plus tempo, meter and key."""
    part = stream.Part()
    part.insert(0, tempo.MetronomeMark(number=melody.tempo_bpm))
    part.insert(0, meter.TimeSignature(melody.time_signature))
    part.insert(0, parse_key(melody.key))
    for n in melody.notes:
        m21 = note.Note(midi=n.pitch, quarterLength=n.duration_beats)
        m21.volume.velocity = n.velocity
        part.insert(n.start_beats, m21)
    return part


def from_stream(part: stream.Stream, template: Melody) -> Melody:
    """The notes of `part` (flattened; a chord keeps its top note) with `template`'s key/tempo."""
    notes = []
    for element in part.flatten().notes:
        pitch = max(p.midi for p in element.pitches)
        velocity = element.volume.velocity if element.volume.velocity is not None else 80
        notes.append(
            Note(
                pitch=int(pitch),
                start_beats=round(float(element.offset), 6),
                duration_beats=round(float(element.quarterLength), 6),
                velocity=int(velocity),
            )
        )
    notes.sort(key=lambda n: (n.start_beats, n.pitch))
    return template.with_notes(notes)
