"""A hum as notes, kept in two forms that never mix.

`Transcription.raw` is what was hummed: each note's pitch, onset, duration and loudness exactly as
the transcriber heard them, in seconds. Nothing quantizes or snaps it, so "play back my hum" and
"export MIDI" reproduce the hum. `Transcription.quantized()` is a separate copy on a beat grid with
every note moved into the detected key, which is what arrangements are built on.

Hearing the hum is the intake's job (hum/engine/audio/intake): basic-pitch finds the notes and the
cleanup keeps the single sung line, steady through vibrato, glides and breaths, with octave ghosts
removed. This module adds what the intake throws away (the raw notes), the tempo and key, the
scale-snapped copy, and a JSON form so a hum is only analysed once.
"""

import contextlib
import io
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import soundfile as sf

from hum.engine.audio.errors import PipelineError
from hum.engine.audio.intake.cleanup import Note, clean_melody
from hum.engine.audio.intake.normalize import normalize, sha256_of
from hum.engine.audio.intake.rhythm import MIN_NOTES_FOR_TEMPO, detect_key, detect_tempo, quantize
from hum.engine.audio.intake.transcribe import transcribe

FORMAT_VERSION = 1

# Pitch classes of the notes a key allows. A minor key also allows its raised seventh, the way tunes
# in minor are sung.
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10, 11)
SCALES = {"major": MAJOR, "minor": MINOR}

NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True)
class HeardNote:
    """A note as hummed. Seconds from the first note's onset, so the first note starts at 0."""

    pitch: int  # MIDI note number (60 = middle C), already corrected for how flat or sharp the hum was
    start: float
    duration: float
    velocity: int  # 1 to 127

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class BeatNote:
    """A note on the beat grid, in the key. Beats from the first note."""

    pitch: int
    start: float
    duration: float
    velocity: int


@dataclass
class Transcription:
    raw: list[HeardNote]
    tempo_bpm: float
    tonic: str  # "C", "Eb", "F#"...
    mode: str  # "major" or "minor"
    tuning_cents: float = 0.0
    fell_back: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((note.end for note in self.raw), default=0.0)

    @property
    def tonic_pitch_class(self) -> int:
        return tonic_pitch_class(self.tonic)

    def quantized(self) -> list[BeatNote]:
        """The tune on the beat grid and inside the key. The raw notes are not touched."""
        heard = [Note(note.start, note.end, note.pitch, note.velocity) for note in self.raw]
        beats = quantize(heard, self.tempo_bpm)
        pitch_class = self.tonic_pitch_class
        return [
            BeatNote(snap_to_scale(note.pitch, pitch_class, self.mode), note.start_beats, note.duration_beats, note.velocity)
            for note in beats
        ]

    def to_json(self) -> dict:
        return {
            "version": FORMAT_VERSION,
            "notes": [asdict(note) for note in self.raw],
            "tempo_bpm": self.tempo_bpm,
            "tonic": self.tonic,
            "mode": self.mode,
            "tuning_cents": self.tuning_cents,
            "fell_back": self.fell_back,
            "warnings": self.warnings,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Transcription":
        if data.get("version") != FORMAT_VERSION:
            raise ValueError("transcription saved by another version")
        return cls(
            raw=[HeardNote(**note) for note in data["notes"]],
            tempo_bpm=data["tempo_bpm"],
            tonic=data["tonic"],
            mode=data["mode"],
            tuning_cents=data.get("tuning_cents", 0.0),
            fell_back=data.get("fell_back", False),
            warnings=data.get("warnings", []),
        )


def tonic_pitch_class(tonic: str) -> int:
    """0 for C ... 11 for B. Accepts sharps and flats ("F#", "Bb", and music21's "B-")."""
    base = _PITCH_CLASS[tonic[0].upper()]
    for mark in tonic[1:]:
        base += 1 if mark == "#" else -1 if mark in "b-" else 0
    return base % 12


def snap_to_scale(pitch: int, tonic_pc: int, mode: str) -> int:
    """The nearest note of the key to `pitch`; a tie goes down. Notes already in the key stay put."""
    allowed = {(tonic_pc + degree) % 12 for degree in SCALES[mode]}
    for distance in (0, 1, 2):
        for candidate in (pitch - distance, pitch + distance):
            if candidate % 12 in allowed:
                return candidate
    return pitch  # unreachable: every note is within two semitones of a major or minor scale


def transcribe_hum(wav_path: str | Path) -> Transcription:
    """Listens to the hum. Raises PipelineError, with a message fit to show the user, when there is
    nothing usable in it (silence, too short, no tune)."""
    path = str(wav_path)
    with tempfile.TemporaryDirectory(prefix="hum-transcribe-") as scratch:
        work = normalize(path, sha256_of(path), scratch)
        with contextlib.redirect_stdout(io.StringIO()):  # basic-pitch prints a line per file
            heard = transcribe(work.path)
        samples, rate = sf.read(work.path, dtype="float32")
    cleaned = clean_melody(heard, samples, rate)
    if not cleaned.notes:
        raise PipelineError("transcription", "No tune was found in that hum. Try humming a little louder.", code="no_tune")

    first = cleaned.notes[0].start
    raw = [
        HeardNote(note.pitch, round(note.start - first, 4), round(note.end - note.start, 4), int(note.velocity))
        for note in cleaned.notes
    ]
    tempo = detect_tempo(cleaned.notes)
    tonic, mode = detect_tonic_and_mode(cleaned.notes, tempo)
    warnings = list(work.warnings) + list(cleaned.warnings)
    if len(cleaned.notes) < MIN_NOTES_FOR_TEMPO:
        warnings.append("The tune was too short to find its tempo, so a moderate tempo was used.")
    return Transcription(raw, tempo, tonic, mode, round(cleaned.tuning_cents, 1), cleaned.fell_back, warnings)


def detect_tonic_and_mode(notes: list[Note], tempo: float) -> tuple[str, str]:
    name = detect_key(quantize(notes, tempo))  # music21's name for it, e.g. "B- major"
    tonic, mode = name.split()
    return NOTE_NAMES[tonic_pitch_class(tonic)], mode


def transcription_for(hum_path: Path, cache_dir: Path) -> Transcription:
    """The hum's transcription, from the saved copy when there is one. Saved next to the other hum
    data, named after the recording (every upload has a name of its own)."""
    saved = cache_dir / f"{hum_path.stem}.json"
    if saved.is_file():
        try:
            return Transcription.from_json(json.loads(saved.read_text()))
        except (ValueError, KeyError, TypeError):
            pass  # unreadable or from another version: hear it again
    result = transcribe_hum(hum_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps(result.to_json()))
    return result
