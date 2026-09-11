"""
Build a pixel box for every bar on a page, so the frontend can highlight
where a piece of feedback happened instead of printing a bar number the
player then has to hunt for on the score.

Inputs are oemer's own detections, already in memory after
png_to_musicxml.convert() runs extract():

    staffs    the `staffs` layer -- Staff instances carrying `group`
              (the system, i.e. one line of music across the page; a piano
              grand staff's treble and bass share one group) and x/y extents
              for their slice of it. oemer splits each staff into several
              x-zones, so one system is many Staff objects.
    barlines  bboxes of the detected barlines, same coordinate space.

A bar's box is the x-span between the two barlines around it and the y-span
of the whole system it sits on (padded a little, so ledger lines, slurs and
accidentals above/below the staff fall inside the highlight).

Two approximations worth knowing about:

  * The leading edge of a system is used as a bar boundary whether or not
    oemer detected a barline there, so a system whose opening barline was
    missed still starts its first bar in the right place. Slivers -- the
    stray sub-measure segments this produces when the barline *was* detected
    right at the system edge -- are dropped (MIN_BAR_WIDTH_FRACTION).
  * Bars are numbered by reading order (top system to bottom, left to
    right), starting at 1. That lines up with the time-derived numbering
    feedback_generator uses (judges/__init__.py::bar_of) as long as the page
    has no pickup measure and no repeats -- neither of which the OMR
    pipeline detects today.
"""

# A segment between two boundaries narrower than this fraction of its
# system's width isn't a bar -- it's the gap between a system-edge barline
# and the staff edge itself.
MIN_BAR_WIDTH_FRACTION = 0.02

# Fraction of a system's own height added above and below its box, to cover
# ledger lines, dynamics and slurs that sit outside the stafflines.
SYSTEM_PADDING_FRACTION = 0.15


def _systems(staffs) -> list:
    """[(x_left, y_upper, x_right, y_lower), ...] -- one entry per system,
    top to bottom. Staff objects are grouped by oemer's `group` attribute
    (see module docstring) rather than by y-overlap, so both halves of a
    grand staff end up in the same system."""
    extents = {}
    for staff in _flatten(staffs):
        group = getattr(staff, "group", None)
        if group is None:
            continue
        box = (
            float(staff.x_left),
            float(staff.y_upper),
            float(staff.x_right),
            float(staff.y_lower),
        )
        current = extents.get(group)
        extents[group] = box if current is None else (
            min(current[0], box[0]),
            min(current[1], box[1]),
            max(current[2], box[2]),
            max(current[3], box[3]),
        )

    # Sort by vertical position rather than by group number: the numbering
    # is oemer's, reading order is what bar numbers follow.
    return [extents[key] for key in sorted(extents, key=lambda g: extents[g][1])]


def _flatten(staffs) -> list:
    """oemer hands back a 2D numpy grid of Staff objects (rows = staves,
    columns = x-zones), with empty cells left as the 0 the grid was
    initialized with."""
    flat = []
    for entry in (staffs.reshape(-1) if hasattr(staffs, "reshape") else staffs):
        flat.extend(entry if isinstance(entry, (list, tuple)) else [entry])
    return [staff for staff in flat if hasattr(staff, "y_upper")]


def _bar_x_spans(system: tuple, barline_xs: list) -> list:
    """[(x_start, x_end), ...] for one system, left to right."""
    x_left, _, x_right, _ = system
    width = x_right - x_left
    if width <= 0:
        return []

    inner = sorted(x for x in barline_xs if x_left < x < x_right)
    boundaries = [x_left] + inner + [x_right]

    minimum = MIN_BAR_WIDTH_FRACTION * width
    return [
        (start, end)
        for start, end in zip(boundaries, boundaries[1:])
        if end - start >= minimum
    ]


def build(barlines, staffs, oemer_image_size: tuple, page_size: tuple) -> list:
    """
    Returns [{"bar", "x", "y", "w", "h"}, ...] for one page, bars numbered
    from 1 in reading order, boxes in the page PNG's pixel space (top-left
    origin, x right / y down).

    `oemer_image_size` is the (w, h) of the working image oemer resized the
    page to -- the space `barlines`/`staffs` live in -- and `page_size` the
    (w, h) of the page PNG itself, which is what the frontend's renderer
    scales from. Returns [] if oemer found no staffs (a page of text, or a
    failed detection).
    """
    systems = _systems(staffs)
    if not systems:
        return []

    barline_xs = [(x1 + x2) / 2 for x1, _, x2, _ in barlines]

    oemer_w, oemer_h = oemer_image_size
    page_w, page_h = page_size
    sx = page_w / oemer_w if oemer_w else 1.0
    sy = page_h / oemer_h if oemer_h else 1.0

    boxes = []
    for x_left, y_upper, x_right, y_lower in systems:
        padding = SYSTEM_PADDING_FRACTION * (y_lower - y_upper)
        top = max(0.0, y_upper - padding)
        bottom = min(float(oemer_h), y_lower + padding)

        for x_start, x_end in _bar_x_spans((x_left, y_upper, x_right, y_lower), barline_xs):
            boxes.append({
                "bar": len(boxes) + 1,
                "x": round(x_start * sx),
                "y": round(top * sy),
                "w": round((x_end - x_start) * sx),
                "h": round((bottom - top) * sy),
            })
    return boxes
