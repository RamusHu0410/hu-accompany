"""pdf_processor isn't a Django app (not in INSTALLED_APPS), so
`python manage.py test` won't auto-discover this file. Run explicitly:

    cd backend
    python manage.py test pdf_processor.tests

Only the parts that are pure geometry are covered here -- running oemer
itself needs a real page and a couple of minutes.

The per-bar pixel-box geometry (`bar_boxes.build`) has moved to its own
package -- see `bar_boxes/tests.py`. What stays here is `_collect_bar_boxes`,
which stitches those per-page boxes onto one piece-wide numbering.
"""

from django.test import TestCase

from .pdf_to_notes import _collect_bar_boxes


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
