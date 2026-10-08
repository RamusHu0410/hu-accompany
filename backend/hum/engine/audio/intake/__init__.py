"""Audio intake, the pipeline's step A: a hummed recording → one clean melody, written to the run
directory as melody_clean.mid and melody.json (see the pipeline contract). Also the checks the
upload route runs on every recording.
"""

from .checks import AudioInputError, inspect_wav, unique_upload_name
from ..errors import PipelineError  # shared with the arrangement step
from .melody import MelodyResult, transcribe_to_melody

__all__ = [
    "AudioInputError",
    "MelodyResult",
    "PipelineError",
    "inspect_wav",
    "transcribe_to_melody",
    "unique_upload_name",
]
