"""Phase 10 - Export.

Writes the final notes.json matching the target schema:
[{"id": 1, "data": {"hz": ..., "start": ..., "duration": ..., "dynamic": ...}}]

This part is real (not a stub) - it just currently exports whatever
phase9_timeline produced, which is an empty list until phases 2-9 land.
"""

import json
import logging
from pathlib import Path

from .models.timeline import NoteEvent


def export(events: list, output_path: Path, logger: logging.Logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [e.to_export_dict() if isinstance(e, NoteEvent) else e for e in events]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("phase10_export: wrote %d note events to %s", len(payload), output_path)
    return output_path
