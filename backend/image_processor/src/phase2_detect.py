"""Phase 2 - Vision Detection (STUB).

Spec: detect every visible object (notes, rests, clefs, accidentals, ...)
without interpreting any of it, storing bbox/confidence/page/staff/crop for
each. Intended implementation: wrap an existing OMR engine (this repo already
vendors an oemer-based pipeline in scripts/pdf_processor.py) and convert its
output into MusicObject records.

Not implemented yet - returns no detections so the pipeline can run end to
end.
"""

import logging

from .models.document import DocumentPreparation


def detect(prep: DocumentPreparation, config, logger: logging.Logger) -> list:
    logger.info("phase2_detect: not yet implemented, returning 0 detections")
    return []
