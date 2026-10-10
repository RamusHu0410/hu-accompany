from pathlib import Path

import pytest

from hum.transcription import transcribe_hum

SAMPLE = Path(__file__).parent / "fixtures" / "hum_sample.wav"


@pytest.fixture(scope="session")
def sample():
    """The real hum fixture, heard once for the whole run: D minor, about 92 bpm, three bars."""
    return transcribe_hum(SAMPLE)
