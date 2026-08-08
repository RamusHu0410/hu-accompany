"""CLI entrypoint for the music score PDF -> note-event pipeline.

Usage:
    python main.py <path/to/score.pdf>
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from config import CONFIG
from src.phase1_prepare import prepare_document
from src.phase2_detect import detect
from src.phase3_classify import classify
from src.phase4_markings import analyze_markings
from src.phase5_reasoning import reason
from src.phase6_ambiguity import resolve
from src.phase7_validation import validate
from src.phase8_reanalysis import reanalyze
from src.phase9_timeline import generate_timeline
from src.phase10_export import export, export_markings
from src.utils.logging_setup import configure_logging


def run(pdf_path: Path, config=CONFIG, notes_path: Path = None, markings_path: Path = None) -> tuple:
    """Runs the full pipeline. `notes_path`/`markings_path` override where the
    final JSON is written (defaults to config.json_dir/notes.json and
    .../markings.json) - the Django integration writes these into storage
    next to the source PDF instead of into this package's own output/
    directory. Debug/cache/log artifacts always stay under config.output_dir
    regardless - those are this package's own working files, not part of the
    contract with callers."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = configure_logging(config.logs_dir, run_id)
    logger.info("starting run %s for %s", run_id, pdf_path)

    timings = {}

    def timed(name, fn, *args):
        start = time.perf_counter()
        result = fn(*args)
        timings[name] = round(time.perf_counter() - start, 3)
        logger.info("%s finished in %.3fs", name, timings[name])
        return result

    prep = timed("phase1_prepare", prepare_document, pdf_path, config, logger)
    objects = timed("phase2_detect", detect, prep, config, logger)
    objects = timed("phase3_classify", classify, objects, config, logger)
    objects = timed("phase4_markings", analyze_markings, objects, prep, config, logger)
    structure = timed("phase5_reasoning", reason, objects, config, logger)
    structure = timed("phase6_ambiguity", resolve, structure, config, logger)
    structure = timed("phase7_validation", validate, structure, config, logger)
    structure = timed("phase8_reanalysis", reanalyze, structure, config, logger)
    events = timed("phase9_timeline", generate_timeline, structure, config, logger)

    notes_path = notes_path or (config.json_dir / "notes.json")
    markings_path = markings_path or (config.json_dir / "markings.json")
    notes_path = timed("phase10_export[notes]", export, events, notes_path, logger)
    markings_path = timed("phase10_export[markings]", export_markings, structure, markings_path, logger)

    logger.info(
        "run %s complete: %d pages ok, %d page errors, %d note events, %d markings, timings=%s",
        run_id,
        len(prep.pages),
        len(prep.page_errors),
        len(events),
        len(structure["markings"]),
        timings,
    )
    return notes_path, markings_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path/to/score.pdf>")
        sys.exit(1)
    notes_path, markings_path = run(Path(sys.argv[1]))
    print(f"Notes JSON    -> {notes_path}")
    print(f"Markings JSON -> {markings_path}")
