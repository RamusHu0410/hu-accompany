"""pdf_processor isn't a Django app (not in INSTALLED_APPS), so
`python manage.py test` won't auto-discover this file. Run explicitly:

    cd backend
    python manage.py test pdf_processor.tests

Only the parts that are pure geometry are covered here -- running oemer
itself needs a real page and a couple of minutes.
"""

from django.test import TestCase

from .part1_notes import bar_boxes
from .pdf_to_notes import _collect_bar_boxes


class FakeStaff:
    """Stands in for an oemer Staff: one x-zone slice of one staff line row.
    `group` is the system it belongs to (both halves of a grand staff share
    one)."""

    def __init__(self, group, x_left, y_upper, x_right, y_lower):
        self.group = group
        self.x_left = x_left
        self.y_upper = y_upper
        self.x_right = x_right
        self.y_lower = y_lower


def system(group, y_upper, y_lower, x_left=0, x_right=1000, zones=2):
    """One system as oemer reports it: several Staff objects tiling it
    left to right."""
    width = (x_right - x_left) / zones
    return [
        FakeStaff(group, x_left + i * width, y_upper, x_left + (i + 1) * width, y_lower)
        for i in range(zones)
    ]


def barline(x, y_upper=0, y_lower=100):
    return (x - 2, y_upper, x + 2, y_lower)


SIZE = (1000, 1000)  # no rescaling, so expected pixels stay readable


class BarBoxTests(TestCase):
    def test_barlines_split_a_system_into_bars_numbered_from_one(self):
        boxes = bar_boxes.build(
            barlines=[barline(250), barline(500), barline(750)],
            staffs=system(0, 100, 200),
            oemer_image_size=SIZE,
            page_size=SIZE,
        )
        self.assertEqual([b["bar"] for b in boxes], [1, 2, 3, 4])
        self.assertEqual([(b["x"], b["w"]) for b in boxes],
                         [(0, 250), (250, 250), (500, 250), (750, 250)])

    def test_system_height_is_padded_beyond_the_stafflines(self):
        box = bar_boxes.build(
            barlines=[barline(500)],
            staffs=system(0, 100, 200),
            oemer_image_size=SIZE,
            page_size=SIZE,
        )[0]
        # 15% of the system's 100px height above and below.
        self.assertEqual((box["y"], box["h"]), (85, 130))

    def test_a_grand_staff_is_one_system_not_two(self):
        staffs = system(0, 100, 200) + system(0, 300, 400)  # treble + bass, same group
        boxes = bar_boxes.build(
            barlines=[barline(500)], staffs=staffs, oemer_image_size=SIZE, page_size=SIZE
        )
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0]["y"], 55)          # padded above the treble staff
        self.assertEqual(boxes[0]["y"] + boxes[0]["h"], 445)  # padded below the bass staff

    def test_bars_are_numbered_down_the_page_across_systems(self):
        staffs = system(1, 500, 600) + system(0, 100, 200)  # lower system listed first
        boxes = bar_boxes.build(
            barlines=[barline(500, 100, 200), barline(500, 500, 600)],
            staffs=staffs, oemer_image_size=SIZE, page_size=SIZE,
        )
        self.assertEqual([(b["bar"], b["y"]) for b in boxes],
                         [(1, 85), (2, 85), (3, 485), (4, 485)])

    def test_a_barline_on_the_system_edge_makes_no_sliver_bar(self):
        boxes = bar_boxes.build(
            barlines=[barline(2), barline(500), barline(998)],
            staffs=system(0, 100, 200),
            oemer_image_size=SIZE,
            page_size=SIZE,
        )
        # Two real bars -- the 2px offcuts either side of the edge barlines
        # are dropped rather than reported as bars of their own.
        self.assertEqual([(b["x"], b["w"]) for b in boxes], [(2, 498), (500, 498)])

    def test_boxes_are_rescaled_from_oemer_to_the_page_png(self):
        boxes = bar_boxes.build(
            barlines=[barline(500)],
            staffs=system(0, 100, 200),
            oemer_image_size=SIZE,
            page_size=(2000, 4000),
        )
        self.assertEqual((boxes[0]["x"], boxes[0]["w"]), (0, 1000))
        self.assertEqual((boxes[0]["y"], boxes[0]["h"]), (340, 520))

    def test_no_staffs_means_no_boxes(self):
        self.assertEqual(
            bar_boxes.build(barlines=[barline(500)], staffs=[],
                            oemer_image_size=SIZE, page_size=SIZE),
            [],
        )


class CollectBarBoxTests(TestCase):
    def page(self, bars, page_size=(1000, 1400)):
        return {
            "page_size": list(page_size),
            "bar_boxes": [{"bar": n, "x": 0, "y": 0, "w": 10, "h": 10} for n in range(1, bars + 1)],
        }

    def test_page_two_continues_page_ones_numbering(self):
        boxes = _collect_bar_boxes([self.page(3), self.page(2)])
        self.assertEqual([(b["bar"], b["page"]) for b in boxes],
                         [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2)])

    def test_every_box_carries_the_size_of_the_page_it_was_measured_on(self):
        boxes = _collect_bar_boxes([self.page(1, (1000, 1400)), self.page(1, (900, 1200))])
        self.assertEqual([b["page_size"] for b in boxes], [[1000, 1400], [900, 1200]])
