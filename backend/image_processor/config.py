"""Central, overridable configuration for the pipeline.

All thresholds/paths live here (spec: "Keep all thresholds configurable")
rather than scattered through phase modules.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")


@dataclass
class Config:
    base_dir: Path = BASE_DIR
    input_dir: Path = BASE_DIR / "input"
    output_dir: Path = BASE_DIR / "output"

    render_dpi: int = int(os.environ.get("PIPELINE_RENDER_DPI", 600))

    # Phase 1 - staff detection heuristics
    min_staff_line_count: int = 5
    staff_line_spacing_tolerance: float = 0.25  # fraction of median spacing
    binarize_threshold: int = 200  # 0-255, pixels darker than this count as "ink"

    @property
    def json_dir(self) -> Path:
        return self.output_dir / "json"

    @property
    def debug_dir(self) -> Path:
        return self.output_dir / "debug"

    @property
    def logs_dir(self) -> Path:
        return self.output_dir / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "cache"


CONFIG = Config()
