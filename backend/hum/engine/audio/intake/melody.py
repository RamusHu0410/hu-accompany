"""Step A of the pipeline contract: transcribe_to_melody(input_path, run_dir) -> MelodyResult.

    intake_original.<ext>   the upload, copied untouched and read-only (its SHA-256 is in the log)
    intake_normalized.wav   the working copy: mono, silent ends trimmed, peak at -1 dBFS
    melody_clean.mid        the melody: one track, monophonic, quantized, program 0
    melody.json             the same notes, with tempo, key, time signature and tuning (the source of truth)
    intake_log.json         what happened: note counts before and after cleanup, settings, warnings

Every file is new in run_dir; nothing is overwritten, and the upload itself is never changed.
Raises PipelineError(step, message, code=...) when the recording can't give a melody (app/audio/errors.py).
"""

import contextlib
import dataclasses
import io
import json
import os
import time
from dataclasses import dataclass, field

import soundfile as sf

from .cleanup import clean_melody
from .config import AUDIO, CLEANUP, TRANSCRIPTION
from ..errors import PipelineError
from .normalize import keep_original, new_file, normalize, sha256_of
from .output import write_melody
from .rhythm import MIN_NOTES_FOR_TEMPO, detect_key, detect_tempo, quantize
from .transcribe import transcribe

LOG_NAME = "intake_log.json"


@dataclass
class MelodyResult:
    midi_path: str
    json_path: str
    note_count: int
    fell_back: bool
    warnings: list[str] = field(default_factory=list)


def transcribe_to_melody(input_path: str, run_dir: str) -> MelodyResult:
    os.makedirs(run_dir, exist_ok=True)
    log: dict = {"input": os.path.abspath(input_path), "settings": _settings()}
    started = time.perf_counter()
    try:
        original, checksum = keep_original(input_path, run_dir)
        log["original"] = {"path": original, "sha256": checksum}
        work = normalize(original, checksum, run_dir)
        log["normalized"] = {"path": work.path, "seconds": round(work.seconds, 3), "sample_rate": work.sample_rate, "channels_in_original": work.channels}

        with contextlib.redirect_stdout(io.StringIO()):  # basic-pitch prints a line per file
            heard = transcribe(work.path)
        samples, rate = sf.read(work.path, dtype="float32")
        cleaned = clean_melody(heard, samples, rate)
        log["notes"] = cleaned.counts
        log["tuning_offset_cents"] = round(cleaned.tuning_cents, 1)
        if not cleaned.notes:
            raise PipelineError("intake.cleanup", "No tune was found in that hum. Try humming a little louder.", code="no_tune")

        tempo = detect_tempo(cleaned.notes)
        notes = quantize(cleaned.notes, tempo)
        bars = (notes[-1].start_beats + notes[-1].duration_beats) / 4
        if bars > CLEANUP.max_bars:
            raise PipelineError("intake.quantize", f"That tune is too long to make into a song. Hum a shorter phrase, up to {CLEANUP.max_bars} bars.", code="too_long")
        key = detect_key(notes)
        midi_path, json_path = write_melody(run_dir, notes, tempo, key, cleaned.tuning_cents)

        if sha256_of(input_path) != checksum:
            raise PipelineError("intake", "The original recording changed while it was being read.", code="input_changed")
        warnings = work.warnings + cleaned.warnings
        if len(cleaned.notes) < MIN_NOTES_FOR_TEMPO:
            warnings.append("The tune was too short to find its tempo, so a moderate tempo was used.")
        log.update(tempo_bpm=tempo, key=key, fell_back=cleaned.fell_back, warnings=warnings)
        return MelodyResult(midi_path, json_path, len(notes), cleaned.fell_back, warnings)
    except PipelineError as error:
        log["error"] = {"step": error.step, "code": error.code, "message": error.message}
        raise
    finally:
        log["seconds"] = round(time.perf_counter() - started, 3)
        _write_log(run_dir, log)


def _write_log(run_dir: str, log: dict) -> None:
    try:
        path = new_file(run_dir, LOG_NAME, "intake")
    except PipelineError:
        return  # a log from an earlier run is there; the run directory wasn't a fresh one
    with open(path, "w") as file:
        json.dump(log, file, indent=2, default=str)


def _settings() -> dict:
    return {name: dataclasses.asdict(value) for name, value in (("transcription", TRANSCRIPTION), ("cleanup", CLEANUP), ("audio", AUDIO))}
