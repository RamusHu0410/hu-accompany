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
from src.phase10_export import export
from src.utils.logging_setup import configure_logging


def run(pdf_path: Path, config=CONFIG) -> Path:
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
    objects = timed("phase4_markings", analyze_markings, objects, config, logger)
    structure = timed("phase5_reasoning", reason, objects, config, logger)
    structure = timed("phase6_ambiguity", resolve, structure, config, logger)
    structure = timed("phase7_validation", validate, structure, config, logger)
    structure = timed("phase8_reanalysis", reanalyze, structure, config, logger)
    events = timed("phase9_timeline", generate_timeline, structure, config, logger)
    output_path = config.json_dir / "notes.json"
    timed("phase10_export", export, events, output_path, logger)

    logger.info(
        "run %s complete: %d pages ok, %d page errors, %d note events, timings=%s",
        run_id,
        len(prep.pages),
        len(prep.page_errors),
        len(events),
        timings,
    )
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path/to/score.pdf>")
        sys.exit(1)
    run(Path(sys.argv[1]))
