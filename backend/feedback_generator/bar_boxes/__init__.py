"""Per-bar pixel boxes for a page, so feedback can be highlighted on the
score instead of only naming a bar number. See bar_boxes.py."""

from .bar_boxes import (
    MIN_BAR_WIDTH_FRACTION,
    SYSTEM_PADDING_FRACTION,
    build,
)

__all__ = ["build", "MIN_BAR_WIDTH_FRACTION", "SYSTEM_PADDING_FRACTION"]
