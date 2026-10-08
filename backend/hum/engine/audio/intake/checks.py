"""Checks an uploaded recording before any analysis runs, and saves it under a name of its own.

Every failure here is an ``AudioInputError`` whose message is safe to show the user, so the
routes can answer 400 with it instead of letting librosa/soundfile blow up deep inside the
pipeline (an empty WAV used to crash ``process_audio`` on ``np.max`` of an empty array).
"""

import os
import re
import unicodedata
import uuid

import soundfile as sf

MIN_DURATION_SECONDS = 0.2  # shorter than this can't hold a single deliberate note
MAX_DURATION_SECONDS = 120.0  # the recorder stops at 10 s; pYIN on minutes of audio takes minutes


class AudioInputError(ValueError):
    """The recording can't be used. The message says why, in words fit for the user."""


def inspect_wav(
    filepath: str,
    min_seconds: float = MIN_DURATION_SECONDS,
    max_seconds: float = MAX_DURATION_SECONDS,
) -> dict:
    """Header facts about a WAV file, or AudioInputError if it's unreadable, empty, too short or too long."""
    if not os.path.isfile(filepath):
        raise AudioInputError("The recording wasn't found on the server.")
    try:
        info = sf.info(filepath)
    except RuntimeError as exc:  # soundfile's LibsndfileError: a bad header, or not audio at all
        raise AudioInputError("That file isn't a readable WAV recording.") from exc
    if info.frames == 0 or info.samplerate <= 0:
        raise AudioInputError("The recording is empty.")
    duration = info.frames / info.samplerate
    if duration < min_seconds:
        raise AudioInputError(f"The recording is too short ({duration:.2f} s). Hum for at least {min_seconds:g} s.")
    if duration > max_seconds:
        raise AudioInputError(f"The recording is too long ({duration:.0f} s). Keep it under {max_seconds:g} s.")
    return {
        "duration": duration,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "format": info.format,
        "subtype": info.subtype,
    }


def secure_filename(filename: str) -> str:
    """The name reduced to ASCII letters, digits, dots, dashes and underscores, so it can't leave a
    folder or name a hidden file. Same idea as werkzeug's function of that name (which Flask brought)."""
    name = unicodedata.normalize("NFKD", filename or "").encode("ascii", "ignore").decode("ascii")
    name = name.replace("/", " ").replace("\\", " ")
    name = re.sub(r"[^A-Za-z0-9_.-]", "", "_".join(name.split()))
    return name.strip("._")


def unique_upload_name(filename: str) -> str:
    """A safe filename that no other upload shares. The browser names every hum 'recording.wav',
    so saving under the client's name made each new hum overwrite everyone else's."""
    stem = os.path.splitext(secure_filename(filename))[0] or "recording"
    return f"{stem}-{uuid.uuid4().hex[:12]}.wav"
