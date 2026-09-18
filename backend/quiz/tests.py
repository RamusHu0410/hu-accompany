"""Tests for the quiz package.

Run with: python -m unittest quiz.tests  (no Django settings needed -- the
modules under test are framework-free, which is half the point of keeping
api.py as the only Django-aware file).
"""

import unittest

from .banks import bank_for, bank_sizes
from .errors import InvalidQuizRequest, UnknownTopic
from .generator import MAX_LENGTH, MIN_LENGTH, generate_quiz
from .models import LEVEL_ARCT, MULTIPLE_CHOICE
from .topic import parse_topic

CHEAT_SHEET = "RCM HISTORY 10 + ARCT CHEAT SHEET\nThe Middle Ages (ad 476 - ad 1450)"


class TopicParsing(unittest.TestCase):
    def test_parses_the_two_line_cheat_sheet_heading(self):
        topic = parse_topic(CHEAT_SHEET)
        self.assertEqual(topic.era_key, "middle_ages")
        self.assertEqual(topic.era_name, "The Middle Ages")
        self.assertTrue(topic.include_arct)
        self.assertEqual(topic.level_label, "RCM History 10 + ARCT")

    def test_bare_era_name_is_enough(self):
        self.assertEqual(parse_topic("baroque").era_key, "baroque")

    def test_history_10_alone_does_not_unlock_arct(self):
        topic = parse_topic("RCM History 10\nThe Baroque Era")
        self.assertFalse(topic.include_arct)
        self.assertEqual(topic.level_label, "RCM History 10")

    def test_longest_alias_wins(self):
        # "classical era" must not be shadowed by the shorter "classical".
        self.assertEqual(parse_topic("The Classical Era").era_key, "classical")

    def test_blank_topic_is_rejected(self):
        with self.assertRaises(InvalidQuizRequest):
            parse_topic("   ")


class Generation(unittest.TestCase):
    def test_generates_the_requested_length(self):
        quiz = generate_quiz(CHEAT_SHEET, length=20, seed=1)
        self.assertEqual(len(quiz.questions), 20)

    def test_draw_is_balanced_across_categories(self):
        quiz = generate_quiz(CHEAT_SHEET, length=20, seed=1)
        counts = {}
        for q in quiz.questions:
            counts[q.category] = counts.get(q.category, 0) + 1
        # Round-robin dealing, so no category may lead another by >1.
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertEqual(len(counts), 4)

    def test_arct_questions_only_appear_when_asked_for(self):
        core = generate_quiz("RCM History 10\nThe Middle Ages", length=60, seed=2)
        self.assertFalse(any(q.level == LEVEL_ARCT for q in core.questions))

        full = generate_quiz(CHEAT_SHEET, length=60, seed=2)
        self.assertTrue(any(q.level == LEVEL_ARCT for q in full.questions))
        self.assertGreater(len(full.questions), len(core.questions))

    def test_length_is_clamped_and_never_exceeds_the_bank(self):
        self.assertEqual(len(generate_quiz(CHEAT_SHEET, length=1, seed=3).questions),
                         MIN_LENGTH)
        huge = generate_quiz(CHEAT_SHEET, length=MAX_LENGTH * 10, seed=3)
        self.assertEqual(len(huge.questions), len(bank_for("middle_ages")))

    def test_seed_makes_the_draw_reproducible(self):
        a = generate_quiz(CHEAT_SHEET, length=12, seed=7)
        b = generate_quiz(CHEAT_SHEET, length=12, seed=7)
        self.assertEqual([q.id for q in a.questions], [q.id for q in b.questions])

    def test_unknown_era_is_distinct_from_a_bad_request(self):
        with self.assertRaises(UnknownTopic):
            generate_quiz("RCM History 10\nThe Gregorian Space Age")

    def test_questions_serialize_with_everything_the_client_grades_on(self):
        quiz = generate_quiz(CHEAT_SHEET, length=10, seed=4)
        for question in quiz.as_dict()["questions"]:
            self.assertTrue(question["prompt"])
            self.assertTrue(question["explanation"])
            self.assertTrue(question["accepted"])
            if question["kind"] == MULTIPLE_CHOICE:
                self.assertIn(question["answer"], question["choices"])


class Banks(unittest.TestCase):
    def test_every_era_has_a_bank_with_all_four_categories(self):
        for era_key, size in bank_sizes().items():
            with self.subTest(era=era_key):
                self.assertGreater(size, 0)
                categories = {q.category for q in bank_for(era_key)}
                self.assertEqual(len(categories), 4, f"{era_key}: {categories}")

    def test_question_ids_are_unique_across_every_bank(self):
        seen = []
        for era_key in bank_sizes():
            seen.extend(q.id for q in bank_for(era_key))
        self.assertEqual(len(seen), len(set(seen)))


if __name__ == "__main__":
    unittest.main()
