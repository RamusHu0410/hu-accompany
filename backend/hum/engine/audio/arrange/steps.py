"""The arrangement half of the pipeline, step by step, each writing new files into the run folder:

    melody.json
      -> transform   -> melody_transformed.json, melody_transformed.mid
      -> orchestrate -> arrangement.mid
      -> render      -> rendered.wav   (32-bit float, SAMPLE_RATE)
      -> effects     -> final.wav      (24-bit; what's saved as the user's recording)

Fallbacks (fell_back=True, with a warning): if the transformations fail, the untransformed melody
goes on; if the effects fail, final.wav is the render without them. Anything else is a
PipelineError naming the step.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import pretty_midi
import soundfile as sf

from . import effects as fx
from .config import get_style, resolve_style
from .ensembles import choose as choose_ensemble
from hum.engine.audio.errors import PipelineError
from .files import copy_atomically, write_atomically
from .melody import load_melody, save_melody_json, save_melody_midi
from .orchestrate import TRACKS, orchestrate
from .render import render
from .settings import DEFAULT, ArrangeSettings
from .transforms import MelodyTooLong, apply_operations, apply_settings, fill, frame
from .validate import validate_midi

logger = logging.getLogger(__name__)

STEPS = ("transform", "orchestrate", "render", "effects")
KIT_NAMES = {0: "standard", 8: "room", 16: "power", 24: "electronic", 25: "TR-808", 32: "jazz", 40: "brush", 48: "orchestra"}

FILES = {
    "melody": "melody.json",
    "melody_midi": "melody_transformed.mid",
    "transform": "melody_transformed.json",
    "orchestrate": "arrangement.mid",
    "render": "rendered.wav",
    "effects": "final.wav",
}

# What each step reads: the main output of the step before it.
STEP_INPUT = {"transform": "melody", "orchestrate": "transform", "render": "orchestrate", "effects": "render"}


@dataclass
class StepReport:
    step: str
    outputs: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    fell_back: bool = False
    seconds: float = 0.0
    info: dict = field(default_factory=dict)  # what the step chose (e.g. the ensemble and its instruments)


@dataclass
class RenderResult:
    final_wav_path: str  # 24-bit
    duration_seconds: float
    fell_back: bool
    warnings: list[str]
    steps: list[StepReport] = field(default_factory=list)
    style: str = ""  # the style used (an unknown word becomes the default)
    ensemble: str = ""  # who played it: orchestra, band, electronic, chamber


def _error(step: str, message: str, code: str) -> PipelineError:
    """A PipelineError for the arrangement step `step`. `message` is shown to users, so it says
    what went wrong in plain words; `code` is for code to check; the technical cause is chained
    (raise ... from exc) and logged."""
    return PipelineError(f"arrange.{step}", message, code=code)


def arrange_and_render(melody_json_path: str, style: str, run_dir: str,
                       settings: ArrangeSettings = DEFAULT) -> RenderResult:
    """The contract's entry point: melody.json -> final.wav, all files in `run_dir`. `settings` are
    a listener's changes on top of the style (tempo, key, instruments...); by default none."""
    run = Path(run_dir)
    run.mkdir(parents=True, exist_ok=True)
    target = run / FILES["melody"]
    source = Path(melody_json_path)
    if not (target.exists() and source.exists() and target.samefile(source)):
        try:
            copy_atomically(source, target, validate=load_melody)
        except (OSError, ValueError) as exc:
            logger.error("transform: can't take %s as the melody: %s", source, exc)
            raise _error("transform", "The melody from your recording couldn't be read.", "bad_melody") from exc
    return run_steps(run, style, settings=settings)


def run_steps(
    run_dir: str | Path,
    style: str,
    start: str = "transform",
    on_step: Callable[[StepReport], None] | None = None,
    soundfont: str | Path | None = None,
    settings: ArrangeSettings = DEFAULT,
) -> RenderResult:
    """Run the steps from `start` to the end. The input `start` needs must already be in `run_dir`."""
    if start not in STEPS:
        raise _error(start, f"Can't start from '{start}'; choose one of {', '.join(STEPS)}.", "unknown_step")
    style, style_warning = resolve_style(style)
    preset = get_style(style)
    run = Path(run_dir)
    needed = run / FILES[STEP_INPUT[start]]
    if not needed.is_file():
        raise _error(start, f"{needed.name} isn't in {run}, so this step can't start.", "missing_input")

    reports: list[StepReport] = []
    for step in STEPS[STEPS.index(start):]:
        began = time.monotonic()
        report = _STEP_FUNCTIONS[step](run, preset, soundfont, settings)
        report.seconds = round(time.monotonic() - began, 3)
        logger.info("%s: %.2f s -> %s%s", step, report.seconds, ", ".join(Path(p).name for p in report.outputs.values()),
                    " (fell back)" if report.fell_back else "")
        for warning in report.warnings:
            logger.warning("%s: %s", step, warning)
        if style_warning and not reports:
            report.warnings.insert(0, style_warning)
        reports.append(report)
        if on_step is not None:
            on_step(report)

    final = run / FILES["effects"]
    return RenderResult(
        final_wav_path=str(final),
        duration_seconds=round(sf.info(str(final)).duration, 3),
        fell_back=any(r.fell_back for r in reports),
        warnings=[w for r in reports for w in r.warnings],
        steps=reports,
        style=style,
        ensemble=next((r.info.get("ensemble", "") for r in reports if r.step == "orchestrate"), ""),
    )


def _transform(run: Path, preset, _soundfont, settings: ArrangeSettings) -> StepReport:
    try:
        melody = load_melody(run / FILES["melody"])
    except (OSError, ValueError) as exc:
        logger.error("transform: melody.json is unusable: %s", exc)
        raise _error("transform", "The melody from your recording couldn't be read.", "bad_melody") from exc

    transformed, warnings, fell_back = _arranged(melody, preset, settings)

    try:
        json_path = save_melody_json(transformed, run / FILES["transform"])
        midi_path = save_melody_midi(transformed, run / FILES["melody_midi"])
    except (OSError, ValueError) as exc:
        logger.error("transform: couldn't write the transformed melody: %s", exc)
        raise _error("transform", "The song couldn't be saved.", "write_failed") from exc
    return StepReport("transform", {"melody": str(json_path), "midi": str(midi_path)}, warnings, fell_back)


def arranged_melody(melody, style: str, settings: ArrangeSettings = DEFAULT):
    """The tune as the arrangement will play it (the listener's settings, then the style's
    variations), without writing or rendering anything: (melody, warnings, fell_back)."""
    return _arranged(melody, get_style(resolve_style(style)[0]), settings)


def _arranged(melody, preset, settings: ArrangeSettings):
    warnings, fell_back = [], False
    try:
        melody = apply_settings(melody, settings)  # the listener's tempo, key and mode first
    except Exception as exc:  # noqa: BLE001 - carry on without them
        fell_back = True
        warnings.append(f"The tempo/key changes couldn't be applied ({exc}); using the melody as sung.")
    try:
        melody = fill(melody, preset.fill_bars)  # a short hum becomes a tune long enough to build
    except Exception as exc:  # noqa: BLE001
        fell_back = True
        warnings.append(f"The tune couldn't be lengthened ({exc}); using it as sung.")
    try:
        transformed = apply_operations(melody, preset.transforms)
    except MelodyTooLong:  # a long tune doesn't need lengthening: not a failure
        transformed = melody
        warnings.append(f"The melody is already {melody.bars} bars long, so this style's variations were left out.")
    except Exception as exc:  # noqa: BLE001 - any failure: carry on with the melody as sung
        transformed, fell_back = melody, True
        warnings.append(f"The transformations failed ({exc}); arranging the untransformed melody.")
    return frame(transformed, preset.intro_bars, preset.outro_bars), warnings, fell_back


def _orchestrate(run: Path, preset, _soundfont, settings: ArrangeSettings) -> StepReport:
    try:
        melody = load_melody(run / FILES["transform"])
        ensemble, orchestration, _ = choose_ensemble(preset, settings.ensemble, settings.variation)
        midi, warnings = orchestrate(melody, orchestration, settings)
        path = write_atomically(
            run / FILES["orchestrate"],
            lambda tmp: midi.write(str(tmp)),
            lambda tmp: validate_midi(tmp, min_tracks=len(TRACKS), music21=True),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("orchestrate: %s", exc)
        raise _error("orchestrate", "Your melody couldn't be arranged for the orchestra.", "arrange_failed") from exc
    instruments = {i.name: (f"{KIT_NAMES.get(i.program, 'drum')} kit" if i.is_drum else pretty_midi.program_to_instrument_name(i.program))
                   for i in midi.instruments}
    return StepReport("orchestrate", {"midi": str(path)}, warnings, info={"ensemble": ensemble, "instruments": instruments})


def _render(run: Path, _preset, soundfont, _settings) -> StepReport:
    try:
        path = render(run / FILES["orchestrate"], run / FILES["render"], soundfont)
    except Exception as exc:  # noqa: BLE001
        logger.error("render: %s", exc)
        raise _error("render", "The arrangement couldn't be turned into sound.", "render_failed") from exc
    return StepReport("render", {"wav": str(path)})


def _effects(run: Path, preset, _soundfont, settings: ArrangeSettings) -> StepReport:
    source, target = run / FILES["render"], run / FILES["effects"]
    _, _, reverb_scale = choose_ensemble(preset, settings.ensemble, settings.variation)
    effects = replace(preset.effects, reverb_wet=min(1.0, preset.effects.reverb_wet * reverb_scale),
                      reverb_room_size=min(1.0, preset.effects.reverb_room_size * (0.5 + reverb_scale / 2)))
    try:
        path = fx.apply_effects(source, target, effects)
        return StepReport("effects", {"wav": str(path)})
    except FileExistsError as exc:
        logger.error("effects: %s", exc)
        raise _error("effects", "The finished song couldn't be saved.", "write_failed") from exc
    except Exception as exc:  # noqa: BLE001 - fall back to the render as it is
        warning = f"The effects failed ({exc}); final.wav is the render without them."
    try:
        path = fx.copy_without_effects(source, target)
    except Exception as exc:  # noqa: BLE001
        logger.error("effects: the effects failed and so did the plain copy: %s", exc)
        raise _error("effects", "The finished song couldn't be saved.", "write_failed") from exc
    return StepReport("effects", {"wav": str(path)}, [warning], fell_back=True)


_STEP_FUNCTIONS = {"transform": _transform, "orchestrate": _orchestrate, "render": _render, "effects": _effects}
