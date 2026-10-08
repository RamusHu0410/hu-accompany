"""The whole audio pipeline: an upload -> intake (clean melody) -> arrangement -> final.wav.

Every run gets its own folder, runs/<run_id>/, holding each step's files and run.json, a log of
what ran, what it wrote, how long it took, and any warnings or fallbacks. Runs never change: a
re-run (say, a new style from a saved melody.json) is a new run that copies what it reuses from
the old one and records it as its parent.

    intake (app/audio/intake, step A)    intake_original.<ext>, intake_normalized.wav,
                                         melody_clean.mid, melody.json, intake_log.json
    arrangement (app/audio/arrange, B)   melody_transformed.json/.mid, arrangement.mid,
                                         rendered.wav, final.wav
    this file                            run.json

Intake is chosen by `get_intake()`: "intake" (hum.engine.audio.intake.transcribe_to_melody, the default)
or "fixture" (ignores the audio and hands over the hand-written fixture melody, for tests and
demos). PIPELINE_INTAKE in the environment picks the default. `_check_handoff` checks whatever
intake wrote against the contract before the arrangement starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from hum.engine.audio.arrange import FILES, STEPS, ArrangeSettings, RenderResult, StepReport, run_steps
from hum.engine.audio.arrange.settings import DEFAULT as DEFAULT_SETTINGS
from hum.engine.audio.arrange.files import copy_atomically, replace_atomically
from hum.engine.audio.arrange.melody import load_melody
from hum.engine.audio.arrange.validate import validate_midi
from hum.engine.audio.errors import PipelineError
from hum.engine.audio.intake import MelodyResult, transcribe_to_melody

BACKEND_ROOT = Path(__file__).resolve().parents[3]
# Outside storage/, which the server serves publicly (hum/paths.py passes its own folder anyway).
DEFAULT_RUNS_DIR = BACKEND_ROOT / "hum_data" / "runs"
LOG_NAME = "run.json"
HUM_INDEX = ".by_hum"  # in the runs folder: <sha256 of a hum> -> the run holding its melody
MELODY_MIDI = "melody_clean.mid"

FIXTURE_JSON = BACKEND_ROOT / "hum" / "tests" / "fixtures" / "melody_sample.json"
FIXTURE_MIDI = BACKEND_ROOT / "hum" / "tests" / "fixtures" / "melody_sample.mid"


@dataclass
class PipelineResult:
    run_id: str
    run_dir: str
    final_wav_path: str
    duration_seconds: float
    fell_back: bool
    warnings: list[str]
    log_path: str
    melody: MelodyResult | None = None
    render: RenderResult | None = None


def _fixture_transcribe(input_path: str, run_dir: str) -> MelodyResult:
    """For tests and demos: ignores the audio and hands over the fixture melody (as new files)."""
    run = Path(run_dir)
    midi = copy_atomically(FIXTURE_MIDI, run / MELODY_MIDI, validate_midi)
    melody_json = copy_atomically(FIXTURE_JSON, run / FILES["melody"], load_melody)
    return MelodyResult(
        midi_path=str(midi),
        json_path=str(melody_json),
        note_count=len(load_melody(melody_json).notes),
        fell_back=False,
        warnings=["This is the fixture melody, not a transcription of the upload."],
    )


INTAKES = {"intake": transcribe_to_melody, "fixture": _fixture_transcribe}


def get_intake(name: str | None = None):
    """The intake function called `name` ("intake" or "fixture"; default PIPELINE_INTAKE, else "intake")."""
    name = name or os.environ.get("PIPELINE_INTAKE") or "intake"
    try:
        return INTAKES[name]
    except KeyError:
        raise PipelineError("pipeline.setup", f"Unknown intake {name!r}; choose intake or fixture.", code="unknown_intake") from None


def _intake_name(fn) -> str:
    return next((name for name, known in INTAKES.items() if known is fn), getattr(fn, "__name__", "custom"))


# --- runs and their log ---------------------------------------------------------------------


def new_run_dir(runs_dir: str | Path | None = None) -> Path:
    """A fresh, empty runs/<run_id>/ (run ids sort by time)."""
    root = Path(runs_dir or os.environ.get("RUNS_DIR") or DEFAULT_RUNS_DIR)
    # Time first (so folders sort by age), then a full random UUID. mkdir refuses an existing
    # folder, so even a collision could never put two runs in one folder.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex
    path = root / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _prepare(run_dir: str | Path | None) -> Path:
    if run_dir is None:
        return new_run_dir()
    path = Path(run_dir)
    if path.exists() and any(path.iterdir()):
        raise PipelineError("pipeline.setup", f"{path} already has files in it; a run needs an empty folder.", code="run_dir_not_empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


class RunLog:
    """run.json, rewritten (atomically) after every step so a crash leaves an accurate log."""

    def __init__(self, run_dir: Path, **fields):
        self.path = run_dir / LOG_NAME
        self.data = {
            "run_id": run_dir.name,
            "created_at": _now(),
            "status": "running",
            "steps": [],
            **fields,
        }
        self.save()

    def step(self, step: str, *, outputs=None, warnings=None, fell_back=False, seconds=None, status="ok",
             error=None, detail=None, info=None):
        self.data["steps"].append({
            "step": step,
            "status": status,
            "finished_at": _now(),
            "seconds": seconds,
            "outputs": {k: Path(v).name for k, v in (outputs or {}).items()},
            "warnings": warnings or [],
            "fell_back": fell_back,
            **({"error": error} if error else {}),
            **({"detail": detail} if detail else {}),
            **(info or {}),
        })
        self.save()

    def arrange_step(self, report: StepReport) -> None:
        self.step(report.step, outputs=report.outputs, warnings=report.warnings,
                  fell_back=report.fell_back, seconds=report.seconds, info=report.info)

    def finish(self, status: str, **fields) -> None:
        self.data.update(status=status, finished_at=_now(), **fields)
        self.save()

    def save(self) -> None:
        text = json.dumps(self.data, indent=2, default=str) + "\n"
        replace_atomically(self.path, lambda tmp: tmp.write_text(text, encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- entry points ---------------------------------------------------------------------------


def run_pipeline(input_path: str, style: str, run_dir: str | None = None, intake=None,
                 settings: ArrangeSettings = DEFAULT_SETTINGS) -> PipelineResult:
    """Upload -> final.wav. `run_dir` must be new or empty; by default runs/<run_id>/ is made.
    `intake` is a name for `get_intake` or a transcribe function (default "intake"); `settings` are
    a listener's changes on top of the style."""
    transcribe = intake if callable(intake) else get_intake(intake)
    run = _prepare(run_dir)
    log = RunLog(run, style=style, start_step="intake", parent_run=None, intake=_intake_name(transcribe),
                 settings=None if settings.is_default else settings.to_dict(),
                 input={"path": str(input_path), "sha256": _sha256(input_path) if Path(input_path).is_file() else None})
    try:
        melody = _intake_into(run, log, transcribe, input_path)
        render = run_steps(run, style, on_step=log.arrange_step, settings=settings)
    except PipelineError as exc:
        _log_failure(log, exc)
        raise
    return _finish(run, log, render, melody)


def run_intake(input_path: str, run_dir: str | None = None, intake=None) -> tuple[Path, MelodyResult]:
    """Only intake: a run folder holding the recording's melody.json (and part A's other files),
    ready for any number of arrangements with rerun(..., from_step="transform")."""
    transcribe = intake if callable(intake) else get_intake(intake)
    run = _prepare(run_dir)
    log = RunLog(run, style=None, start_step="intake", parent_run=None, intake=_intake_name(transcribe),
                 input={"path": str(input_path), "sha256": _sha256(input_path) if Path(input_path).is_file() else None})
    try:
        melody = _intake_into(run, log, transcribe, input_path)
    except PipelineError as exc:
        _log_failure(log, exc)
        raise
    log.finish("ok", melody=FILES["melody"], note_count=melody.note_count, fell_back=melody.fell_back, warnings=melody.warnings)
    return run, melody


def melody_run_for(input_path: str, runs_dir: str | Path | None = None, intake=None) -> tuple[Path, list[str]]:
    """The run holding this recording's melody, and intake's warnings: an earlier one for the same
    recording (by checksum) if there is one, else a new intake run. So changing a song's settings
    arranges the same melody again instead of transcribing the hum again."""
    index = Path(runs_dir or os.environ.get("RUNS_DIR") or DEFAULT_RUNS_DIR) / HUM_INDEX
    checksum = _sha256(input_path)
    saved = index / checksum
    if saved.is_file():
        run = saved.parent.parent / saved.read_text().strip()
        if (run / FILES["melody"]).is_file() and (run / LOG_NAME).is_file():
            return run, json.loads((run / LOG_NAME).read_text()).get("warnings", [])
    run, melody = run_intake(input_path, str(new_run_dir(runs_dir)), intake)
    index.mkdir(parents=True, exist_ok=True)
    replace_atomically(saved, lambda tmp: tmp.write_text(run.name))
    return run, melody.warnings


def _intake_into(run: Path, log: RunLog, transcribe, input_path) -> MelodyResult:
    started = datetime.now(timezone.utc)
    try:
        melody = transcribe(str(input_path), str(run))
        _check_handoff(run, melody)
    except PipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("intake", "Your recording couldn't be turned into notes.", code="intake_failed") from exc
    log.step("intake", outputs={"midi": melody.midi_path, "melody": melody.json_path},
             warnings=melody.warnings, fell_back=melody.fell_back,
             seconds=round((datetime.now(timezone.utc) - started).total_seconds(), 3))
    return melody


def rerun(from_run_dir: str | Path, style: str, from_step: str = "transform",
          run_dir: str | None = None, settings: ArrangeSettings = DEFAULT_SETTINGS) -> PipelineResult:
    """A new run that reuses a saved run's files up to `from_step` and redoes the rest in `style`.

    from_step="transform" re-arranges the saved melody.json (with `settings`, if any); "render"
    re-renders the saved arrangement; "effects" only reapplies effects, and so on. The saved run
    isn't touched.
    """
    source = Path(from_run_dir)
    if from_step not in STEPS:
        raise PipelineError("pipeline.rerun", f"Can't re-run from '{from_step}'; choose one of {', '.join(STEPS)}.", code="unknown_step")
    run = _prepare(run_dir)
    log = RunLog(run, style=style, start_step=from_step, parent_run=str(source),
                 settings=None if settings.is_default else settings.to_dict())
    try:
        # Everything the steps before `from_step` produced, copied as new files.
        reused = [FILES["melody"], MELODY_MIDI]
        for step in STEPS[: STEPS.index(from_step)]:
            reused += [FILES[step]] + ([FILES["melody_midi"]] if step == "transform" else [])
        copied = {}
        for name in reused:
            if (source / name).is_file():
                copied[name] = str(copy_atomically(source / name, run / name))
        log.step("reuse", outputs=copied, seconds=0.0)
        render = run_steps(run, style, start=from_step, on_step=log.arrange_step, settings=settings)
    except PipelineError as exc:
        _log_failure(log, exc)
        raise
    return _finish(run, log, render, None)


def _log_failure(log: RunLog, exc: PipelineError) -> None:
    """The user-facing message, plus the technical cause for whoever debugs it."""
    detail = f"{type(exc.__cause__).__name__}: {exc.__cause__}" if exc.__cause__ else None
    log.step(exc.step, status="failed", error=exc.message, detail=detail)
    log.finish("failed", error=str(exc), code=getattr(exc, "code", None), detail=detail)


def _check_handoff(run: Path, melody: MelodyResult) -> None:
    """Intake's files are where the contract says, parse, and agree on the notes."""
    json_path, midi_path = Path(melody.json_path), Path(melody.midi_path)
    if json_path != run / FILES["melody"] or midi_path != run / MELODY_MIDI:
        raise PipelineError("intake", f"Intake wrote {json_path.name}/{midi_path.name} outside the contract's names.", code="bad_handoff")
    try:
        notes = load_melody(json_path).notes
        midi = validate_midi(midi_path)
    except (OSError, ValueError) as exc:
        raise PipelineError("intake", "The melody from your recording couldn't be read.", code="bad_handoff") from exc
    midi_notes = sum(len(i.notes) for i in midi.instruments)
    if midi_notes != len(notes):
        melody.warnings.append(
            f"melody_clean.mid has {midi_notes} notes but melody.json has {len(notes)}; using melody.json."
        )


def _finish(run: Path, log: RunLog, render: RenderResult, melody: MelodyResult | None) -> PipelineResult:
    warnings = (melody.warnings if melody else []) + render.warnings
    fell_back = render.fell_back or bool(melody and melody.fell_back)
    log.finish("ok", final=Path(render.final_wav_path).name, duration_seconds=render.duration_seconds,
               style_used=render.style, ensemble=render.ensemble, fell_back=fell_back, warnings=warnings)
    return PipelineResult(
        run_id=run.name,
        run_dir=str(run),
        final_wav_path=render.final_wav_path,
        duration_seconds=render.duration_seconds,
        fell_back=fell_back,
        warnings=warnings,
        log_path=str(log.path),
        melody=melody,
        render=render,
    )


def main(argv: list[str] | None = None) -> None:
    """Command line:

        python -m hum.engine.audio.pipeline run <upload.wav> [--style cinematic] [--intake intake|fixture]
                                                 [--ensemble orchestra|band|electronic|chamber] [--variation N]
        python -m hum.engine.audio.pipeline rerun <run_dir> <style> [--from transform|orchestrate|render|effects]
                                                 [--ensemble ...] [--variation N]
        python -m hum.engine.audio.pipeline describe <run_dir>
        python -m hum.engine.audio.pipeline stems <run_dir>
    """
    import argparse
    import logging

    from dotenv import load_dotenv

    from hum.engine.audio.arrange import debug
    from hum.engine.audio.arrange.ensembles import ENSEMBLES

    load_dotenv(BACKEND_ROOT / ".env")  # SOUNDFONT_PATH, RUNS_DIR, PIPELINE_INTAKE
    parser = argparse.ArgumentParser(prog="python -m hum.engine.audio.pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each step as it runs")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="an upload through the whole pipeline")
    run_cmd.add_argument("input")
    run_cmd.add_argument("--style", default="cinematic")
    run_cmd.add_argument("--intake", default=None)
    for command in (run_cmd,):
        command.add_argument("--ensemble", choices=sorted(ENSEMBLES), help="who plays (default: the style's own orchestra)")
        command.add_argument("--variation", type=int, help="picks the instruments (and the ensemble, if none is named)")
    rerun_cmd = commands.add_parser("rerun", help="a new run from a saved run's step")
    rerun_cmd.add_argument("run_dir")
    rerun_cmd.add_argument("style")
    rerun_cmd.add_argument("--from", dest="from_step", default="transform", choices=STEPS)
    rerun_cmd.add_argument("--ensemble", choices=sorted(ENSEMBLES), help="who plays (default: the style's own orchestra)")
    rerun_cmd.add_argument("--variation", type=int, help="picks the instruments (and the ensemble, if none is named)")
    commands.add_parser("describe", help="a report of a run").add_argument("run_dir")
    commands.add_parser("stems", help="each track of a run rendered alone").add_argument("run_dir")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.command == "describe":
        print(debug.describe(args.run_dir))
        return
    if args.command == "stems":
        for path in debug.render_stems(args.run_dir):
            print(path)
        return
    settings = ArrangeSettings(ensemble=args.ensemble, variation=args.variation)
    if args.command == "rerun":
        result = rerun(args.run_dir, args.style, args.from_step, settings=settings)
    else:
        result = run_pipeline(args.input, args.style, intake=args.intake, settings=settings)
    print(debug.describe(result.run_dir))
    print(f"\nfinal: {result.final_wav_path}")


if __name__ == "__main__":
    main()


__all__ = ["MelodyResult", "PipelineError", "PipelineResult", "get_intake", "melody_run_for", "new_run_dir", "rerun", "run_intake", "run_pipeline"]
