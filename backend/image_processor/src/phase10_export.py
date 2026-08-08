"""Phase 10 - Export.

Writes the final notes.json matching the target schema:
[{"id": 1, "data": {"hz": ..., "start": ..., "duration": ..., "dynamic": ...}}]

and markings.json (the composer-marking timeline from Phase 4/5/6):
[{"measure": 1, "beat": 0, "type": "tempo", "value": "Allegro"}, ...]
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


def export_markings(structure: dict, output_path: Path, logger: logging.Logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"measure": mk["measure"], "beat": mk["beat"], "type": mk["type"], "value": mk["value"]}
        for mk in structure.get("markings", [])
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("phase10_export: wrote %d markings to %s", len(payload), output_path)
    return output_path
