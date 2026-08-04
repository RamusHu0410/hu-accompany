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

    # Phase 2 - oemer detection performance knobs.
    # oemer's models scan the page in sliding windows and average overlaps;
    # its own default step (128px) overlaps both windows below by ~50%,
    # i.e. runs ~4-5x more inference than the page area requires. Setting
    # step = window size gives full coverage with zero overlap (256/288 are
    # the models' own input sizes - see oemer's checkpoints/*/metadata.pkl).
    oemer_unet_step_size: int = 256
    oemer_seg_step_size: int = 288
    # How many pages to run oemer on concurrently (separate processes -
    # oemer's internal layer state is process-global, not thread-safe) and
    # how many onnxruntime threads each of those processes gets. Their
    # product should stay near the machine's core count to avoid the
    # workers contending with each other for the same cores.
    oemer_max_workers: int = max(1, (os.cpu_count() or 4) // 2)
    oemer_threads_per_worker: int = 2

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
