"""Per-run logging setup.

The spec requires structured debug logs and timing stats per phase, which
plain print() can't give us, so this is the one place in the pipeline that
uses stdlib `logging` (every log line also lands in a per-run file under
output/logs/ for post-hoc debugging).
"""

import logging
import sys
from pathlib import Path


def configure_logging(log_dir: Path, run_id: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{run_id}.log"

    logger = logging.getLogger(f"pipeline.{run_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
