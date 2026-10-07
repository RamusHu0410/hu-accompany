"""basic-pitch: the working copy → its raw notes and its pitch contour, both in memory.

basic-pitch (0.4.0) runs its ONNX model with onnxruntime here; Python 3.14 has no TensorFlow for it
(backend/pyproject.toml). The model is loaded once and reused. predict() takes a file path; nothing
it could write (MIDI, CSV, debug files) is written.
"""

import logging
import warnings
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .config import TRANSCRIPTION, TranscriptionSettings
from ..errors import PipelineError

STEP = "intake.transcribe"


@dataclass(frozen=True, order=True)
class RawNote:
    start: float  # seconds
    end: float
    pitch: int  # MIDI note number
    amplitude: float  # 0 to 1


@dataclass
class Transcription:
    notes: list[RawNote]
    contour: np.ndarray  # (frames, contour bins): how likely each pitch is in each frame, 0 to 1
    frame_times: np.ndarray  # seconds, one per frame


@lru_cache(maxsize=1)
def _basic_pitch():
    """basic-pitch's functions and its ONNX model, loaded once. On import it warns about every
    backend it didn't find (TensorFlow, CoreML, TFLite) and its resampy about pkg_resources; both
    are expected here, so they're kept out of the server log."""
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from basic_pitch import ICASSP_2022_MODEL_PATH
            from basic_pitch.inference import Model, predict
            from basic_pitch.note_creation import model_frames_to_time
    finally:
        root.setLevel(level)
    return predict, Model(ICASSP_2022_MODEL_PATH), model_frames_to_time


def transcribe(wav_path: str, settings: TranscriptionSettings = TRANSCRIPTION) -> Transcription:
    predict, model, model_frames_to_time = _basic_pitch()

    try:
        output, _midi, events = predict(
            wav_path,
            model,
            onset_threshold=settings.onset_threshold,
            frame_threshold=settings.frame_threshold,
            minimum_note_length=settings.minimum_note_length,
            minimum_frequency=settings.minimum_frequency,
            maximum_frequency=settings.maximum_frequency,
            multiple_pitch_bends=settings.multiple_pitch_bends,
            melodia_trick=settings.melodia_trick,
        )
    except Exception as exc:  # noqa: BLE001 - the model failing is a bug or a broken install, not the user's hum
        raise PipelineError(STEP, "The notes couldn't be worked out from that recording. Try again.", code="transcription_failed") from exc
    notes = sorted(RawNote(float(s), float(e), int(p), float(a)) for s, e, p, a, _bends in events)
    contour = output["contour"]
    return Transcription(notes, contour, model_frames_to_time(contour.shape[0]))
