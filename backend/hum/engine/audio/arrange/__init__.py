"""The back half of the audio pipeline: a clean melody (melody.json) -> transformations ->
orchestral multi-track MIDI -> FluidSynth render -> effects -> final 24-bit WAV.

See steps.py for the files each step writes, and config.py for the styles.
"""

from .config import STYLES
from .settings import ArrangeSettings, ExtraPart
from hum.engine.audio.errors import PipelineError  # shared with intake
from .steps import FILES, STEPS, RenderResult, StepReport, arrange_and_render, arranged_melody, run_steps

__all__ = [
    "FILES",
    "STEPS",
    "STYLES",
    "ArrangeSettings",
    "ExtraPart",
    "PipelineError",
    "RenderResult",
    "StepReport",
    "arrange_and_render",
    "arranged_melody",
    "run_steps",
]
