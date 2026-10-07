"""A listening test: render the fixture, print what every step decided, and (if asked) play it.

    cd backend/src
    uv run pytest tests/audio/arrange/test_arrange_listen.py -s --log-cli-level=DEBUG

    LISTEN=1 ...                  also play each result (macOS afplay)
    STYLES=pop,modern ...         which styles (default: cinematic)
    ENSEMBLES=band,electronic ... who plays: orchestra, band, electronic, chamber, or all
                                  (default: the style's own orchestra)
    VARIATION=3 ...               which instruments within the ensemble (default: 0)

The files stay in backend/hum_data/runs/<run_id>/ afterwards, and the test prints their paths.
"""

import os
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from hum.engine.audio import pipeline
from hum.engine.audio.arrange import ArrangeSettings, debug
from hum.engine.audio.arrange.ensembles import ENSEMBLES as ALL_ENSEMBLES

STYLES = [s.strip() for s in os.environ.get("STYLES", "cinematic").split(",") if s.strip()]
_asked = os.environ.get("ENSEMBLES", "").strip()
ENSEMBLES = sorted(ALL_ENSEMBLES) if _asked == "all" else [e.strip() for e in _asked.split(",") if e.strip()] or [None]
VARIATION = int(os.environ.get("VARIATION", "0"))


@pytest.mark.parametrize("ensemble", ENSEMBLES)
@pytest.mark.parametrize("style", STYLES)
def test_listen(style, ensemble, soundfont):
    settings = ArrangeSettings(ensemble=ensemble, variation=VARIATION) if ensemble else ArrangeSettings()
    result = pipeline.run_pipeline(str(pipeline.FIXTURE_MIDI), style, intake="fixture", settings=settings)

    print("\n" + debug.describe(result.run_dir))
    print(f"\n>>> listen: {result.final_wav_path}")

    audio, rate = sf.read(result.final_wav_path)
    assert rate == 48_000 and sf.info(result.final_wav_path).subtype == "PCM_24"
    assert np.all(np.isfinite(audio)) and np.max(np.abs(audio)) <= 1.0
    assert np.sqrt(np.mean(audio ** 2)) > 0.01, "the result is (nearly) silent"
    assert not result.fell_back, result.warnings

    if os.environ.get("LISTEN") == "1":
        if shutil.which("afplay") is None:
            pytest.skip("LISTEN=1 needs afplay (macOS); open the file above instead")
        subprocess.run(["afplay", result.final_wav_path], check=True)
