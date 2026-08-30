"""feedback_generator isn't a Django app (not in INSTALLED_APPS), so
`python manage.py test` won't auto-discover this file. Run explicitly:

    cd backend
    python manage.py test feedback_generator.tests
"""

from unittest.mock import patch

from django.test import TestCase

from . import pedaling
from .alignment import align_notes
from .analysis import (
    analyze_phrase,
    build_extra_error,
    build_missing_error,
    compute_articulation_score,
    compute_overall_score,
    detect_articulation_error,
    detect_duration_error,
    detect_pitch_error,
    detect_timing_error,
)
from .models import ExpectedNote, UserNote
from .nlg import build_immediate_feedback, build_main_feedback, build_positive_feedback, build_summary
from .orchestrator import generate_feedback
from .pitch_utils import hz_to_cents, hz_to_note_name


def expected(note_id=0, hz=440.0, start=0.0, dur=500.0, markings=None):
    return ExpectedNote(
        note_id=note_id, pitch_hz=hz, start_time_ms=start, end_time_ms=start + dur, duration_ms=dur, markings=markings
    )


def user(hz=440.0, start=0.0, dur=500.0, note_id=None):
    return UserNote(pitch_hz=hz, start_time_ms=start, end_time_ms=start + dur, duration_ms=dur, note_id=note_id)


class HzConversionTests(TestCase):
    def test_hz_to_cents_is_zero_for_identical_pitch(self):
        self.assertAlmostEqual(hz_to_cents(440.0, 440.0), 0.0)

    def test_hz_to_cents_one_octave_is_1200(self):
        self.assertAlmostEqual(hz_to_cents(880.0, 440.0), 1200.0, places=3)

    def test_hz_to_note_name_a4(self):
        self.assertEqual(hz_to_note_name(440.0), "A4")

    def test_hz_to_note_name_g4(self):
        # G4 ~= 392.00 Hz
        self.assertEqual(hz_to_note_name(392.0), "G4")


class AlignmentTests(TestCase):
    def test_exact_match(self):
        e = [expected(note_id=1, hz=440.0, start=0.0)]
        u = [user(note_id=1, hz=440.0, start=0.0)]
        result = align_notes(e, u, bpm=120)
        self.assertEqual(len(result.matched), 1)
        self.assertEqual(result.missing, [])
        self.assertEqual(result.extra, [])

    def test_timing_deviation_within_window_still_matches(self):
        e = [expected(note_id=1, hz=440.0, start=1000.0)]
        u = [user(note_id=1, hz=440.0, start=1080.0)]  # 80ms late, within window at 120bpm
        result = align_notes(e, u, bpm=120)
        self.assertEqual(len(result.matched), 1)

    def test_note_outside_window_is_missing_and_extra(self):
        e = [expected(note_id=1, hz=440.0, start=0.0)]
        u = [user(note_id=1, hz=440.0, start=5000.0)]  # way outside any window
        result = align_notes(e, u, bpm=120)
        self.assertEqual(result.matched, [])
        self.assertEqual(len(result.missing), 1)
        self.assertEqual(len(result.extra), 1)

    def test_leftover_user_note_is_extra(self):
        e = [expected(note_id=1, hz=440.0, start=0.0)]
        u = [user(note_id=1, hz=440.0, start=0.0), user(note_id=2, hz=550.0, start=500.0)]
        result = align_notes(e, u, bpm=120)
        self.assertEqual(len(result.matched), 1)
        self.assertEqual(len(result.extra), 1)

    def test_duplicate_note_id_keeps_longest_duration(self):
        e = [expected(note_id=1, hz=440.0, start=0.0, dur=500.0)]
        u = [user(note_id=1, hz=440.0, start=0.0, dur=100.0), user(note_id=1, hz=440.0, start=0.0, dur=480.0)]
        result = align_notes(e, u, bpm=120)
        self.assertEqual(len(result.matched), 1)
        self.assertEqual(result.matched[0][1].duration_ms, 480.0)
        self.assertEqual(result.extra, [])

    def test_id_hint_rejected_when_outside_window(self):
        # Same note_id, but way outside the timing window -- must not be
        # blindly trusted; falls back to windowed matching against nothing.
        e = [expected(note_id=1, hz=440.0, start=0.0)]
        u = [user(note_id=1, hz=440.0, start=10000.0)]
        result = align_notes(e, u, bpm=120)
        self.assertEqual(result.matched, [])
        self.assertEqual(len(result.missing), 1)
        self.assertEqual(len(result.extra), 1)


class PitchErrorDetectionTests(TestCase):
    def test_insignificant_deviation_is_not_an_error(self):
        e, u = expected(hz=440.0), user(hz=442.0)  # ~8 cents
        self.assertIsNone(detect_pitch_error(e, u))

    def test_minor_pitch_error(self):
        e, u = expected(hz=440.0), user(hz=449.0)  # ~35 cents -- inside the 25-50 cent "minor" band
        error = detect_pitch_error(e, u)
        self.assertIsNotNone(error)
        self.assertEqual(error.severity, "minor")

    def test_major_wrong_note_message(self):
        e, u = expected(note_id=12, hz=392.0), user(hz=369.99)  # G vs F#
        error = detect_pitch_error(e, u)
        self.assertEqual(error.severity, "major")
        items = build_immediate_feedback([error])
        self.assertIn("F#", items[0].message)
        self.assertIn("G", items[0].message)
        self.assertEqual(items[0].note_id, 12)
        self.assertEqual(items[0].category, "pitch")


class TimingErrorDetectionTests(TestCase):
    def test_small_offset_at_slow_tempo_is_insignificant(self):
        e, u = expected(start=1000.0), user(start=1005.0)
        self.assertIsNone(detect_timing_error(e, u, bpm=60))

    def test_large_offset_is_major(self):
        e, u = expected(start=1000.0), user(start=1300.0)
        error = detect_timing_error(e, u, bpm=120)
        self.assertIsNotNone(error)
        self.assertEqual(error.severity, "major")

    def test_same_absolute_offset_scored_differently_at_different_tempo(self):
        e, u = expected(start=1000.0), user(start=1060.0)  # 60ms
        slow = detect_timing_error(e, u, bpm=60)  # long beat -> insignificant
        fast = detect_timing_error(e, u, bpm=200)  # short beat -> significant
        self.assertIsNone(slow)
        self.assertIsNotNone(fast)


class DurationErrorDetectionTests(TestCase):
    def test_small_duration_diff_on_short_note_is_insignificant(self):
        e, u = expected(dur=100.0), user(dur=110.0)  # 10ms diff, below floor
        self.assertIsNone(detect_duration_error(e, u))

    def test_large_duration_diff_is_major(self):
        e, u = expected(dur=500.0), user(dur=200.0)
        error = detect_duration_error(e, u)
        self.assertIsNotNone(error)
        self.assertEqual(error.severity, "major")
        self.assertEqual(error.detail["direction"], "too_short")


class MissingExtraNoteTests(TestCase):
    def test_missing_is_major(self):
        self.assertEqual(build_missing_error(expected()).severity, "major")

    def test_extra_is_major(self):
        self.assertEqual(build_extra_error(user()).severity, "major")


class ArticulationScoreTests(TestCase):
    def test_no_markings_anywhere_gives_none(self):
        alignment = align_notes([expected(note_id=1)], [user(note_id=1)], bpm=120)
        self.assertIsNone(compute_articulation_score(alignment))

    def test_staccato_note_held_too_long_is_flagged(self):
        e = expected(note_id=1, dur=500.0, markings="staccato")
        u = user(note_id=1, dur=490.0)  # almost full length, not detached
        error = detect_articulation_error(e, u)
        self.assertIsNotNone(error)
        self.assertEqual(error.category, "articulation")

    def test_staccato_note_played_short_is_fine(self):
        e = expected(note_id=1, dur=500.0, markings="staccato")
        u = user(note_id=1, dur=200.0)
        self.assertIsNone(detect_articulation_error(e, u))


class DynamicsScoreGapTests(TestCase):
    def test_dynamics_is_always_none(self):
        alignment = align_notes([expected(note_id=1)], [user(note_id=1)], bpm=120)
        analysis = analyze_phrase(alignment, bpm=120)
        self.assertIsNone(analysis.scores.dynamics)


class ScoreComputationTests(TestCase):
    def test_overall_renormalizes_over_available_categories(self):
        overall = compute_overall_score({"pitch": 100, "rhythm": None, "tempo": None, "dynamics": None, "articulation": None})
        self.assertEqual(overall, 100)

    def test_overall_is_none_when_everything_is_none(self):
        overall = compute_overall_score({"pitch": None, "rhythm": None, "tempo": None, "dynamics": None, "articulation": None})
        self.assertIsNone(overall)


class MainFeedbackPrioritizationTests(TestCase):
    def test_caps_at_three_and_ranks_major_pitch_above_minor_articulation(self):
        expected_notes = [
            expected(note_id=i, hz=440.0, start=i * 500.0, dur=400.0, markings="staccato" if i >= 3 else None)
            for i in range(6)
        ]
        user_notes = []
        for i, e in enumerate(expected_notes):
            if i < 3:
                user_notes.append(user(note_id=i, hz=369.99, start=e.start_time_ms, dur=e.duration_ms))  # wrong pitch, major
            else:
                user_notes.append(user(note_id=i, hz=440.0, start=e.start_time_ms, dur=320.0))  # ratio 0.8 -- minor staccato miss
        alignment = align_notes(expected_notes, user_notes, bpm=120)
        analysis = analyze_phrase(alignment, bpm=120)
        main_feedback = build_main_feedback(analysis.errors, analysis.tempo_drift, bpm=120)
        self.assertLessEqual(len(main_feedback), 3)
        if main_feedback:
            self.assertEqual(main_feedback[0].category, "pitch")

    def test_empty_when_no_errors(self):
        e = [expected(note_id=1)]
        u = [user(note_id=1)]
        alignment = align_notes(e, u, bpm=120)
        analysis = analyze_phrase(alignment, bpm=120)
        self.assertEqual(build_main_feedback(analysis.errors, analysis.tempo_drift, bpm=120), [])


class PositiveFeedbackTests(TestCase):
    def test_no_forced_praise_when_nothing_qualifies(self):
        from .models import ScoreBreakdown

        scores = ScoreBreakdown(overall=70, pitch=70, rhythm=70, tempo=70, dynamics=None, articulation=None)
        self.assertEqual(build_positive_feedback(scores, []), [])

    def test_high_score_not_flagged_as_problem_is_praised(self):
        from .models import ScoreBreakdown

        scores = ScoreBreakdown(overall=95, pitch=95, rhythm=95, tempo=95, dynamics=None, articulation=None)
        praise = build_positive_feedback(scores, [])
        self.assertTrue(any("Pitch" in p for p in praise))


class SummaryTemplateTests(TestCase):
    def test_combines_positive_and_problem_clauses(self):
        from .models import MainFeedbackItem

        main = [MainFeedbackItem(category="tempo", severity="major", description="The tempo gradually slows across the phrase.", practice_action="x")]
        positive = ["Pitch accuracy was strong."]
        summary = build_summary(main, positive)
        self.assertIn("strong", summary)
        self.assertIn("tempo", summary.lower())

    def test_no_significant_issues_message_when_nothing_to_report(self):
        self.assertIn("No significant issues", build_summary([], []))


class GenerateFeedbackOrchestratorTests(TestCase):
    def test_response_shape_matches_spec(self):
        result = generate_feedback(
            phrase=0,
            bpm=96.0,
            expected_notes=[
                {
                    "note_id": 12, "pitch_hz": 392.0, "start_time_ms": 1000.0,
                    "end_time_ms": 1500.0, "duration_ms": 500.0,
                    "vibrato_depth": None, "pedal_action": None, "has_accent": None, "markings": None,
                }
            ],
            user_notes=[
                {"note_id": 12, "pitch_hz": 369.99, "start_time_ms": 1000.0, "end_time_ms": 1500.0, "duration_ms": 500.0}
            ],
        )
        self.assertEqual(result["phrase"], 0)
        self.assertEqual(len(result["immediate_feedback"]), 1)
        item = result["immediate_feedback"][0]
        self.assertEqual(item["type"], "immediate")
        self.assertEqual(item["category"], "pitch")
        self.assertEqual(item["note_id"], 12)
        summary = result["phrase_summary"]
        self.assertEqual(summary["type"], "phrase_summary")
        self.assertEqual(summary["phrase"], 0)
        self.assertIn("scores", summary)
        for key in ("overall", "pitch", "rhythm", "tempo", "dynamics", "articulation"):
            self.assertIn(key, summary["scores"])
        self.assertIsNone(summary["scores"]["dynamics"])

    def test_missing_required_field_raises_invalid_note_data(self):
        from .errors import InvalidNoteData

        with self.assertRaises(InvalidNoteData):
            generate_feedback(
                phrase=0, bpm=96.0,
                expected_notes=[{"note_id": 1, "pitch_hz": 440.0}],  # missing timing fields
                user_notes=[],
            )


class AnalyzePedalingPlaceholderTests(TestCase):
    def test_returns_none_for_arbitrary_input(self):
        self.assertIsNone(pedaling.analyze_pedaling(object(), object()))
        self.assertIsNone(pedaling.analyze_pedaling(None, None))

    def test_generate_feedback_never_calls_it(self):
        with patch("feedback_generator.pedaling.analyze_pedaling", side_effect=AssertionError("must not be called")):
            generate_feedback(
                phrase=0, bpm=120.0,
                expected_notes=[{"note_id": 1, "pitch_hz": 440.0, "start_time_ms": 0.0, "end_time_ms": 500.0, "duration_ms": 500.0}],
                user_notes=[],
            )
