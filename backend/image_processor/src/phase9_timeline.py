"""Phase 9 - Timeline Generation (STUB).

Spec: convert validated notation into chronological NoteEvent records
(frequency, start time, duration, dynamic, measure, beat, voice).

Not implemented yet - returns no events (the validated structure carries no
notes until phases 2-8 are implemented).
"""

import logging

from .models.timeline import NoteEvent


def generate_timeline(structure: dict, config, logger: logging.Logger) -> list:
    logger.info("phase9_timeline: not yet implemented, returning 0 events")
    events: list[NoteEvent] = []
    return events
