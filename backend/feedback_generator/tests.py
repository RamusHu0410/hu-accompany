"""feedback_generator isn't a Django app (not in INSTALLED_APPS), so
`python manage.py test` won't auto-discover this file. Run explicitly:

    cd backend
    python manage.py test feedback_generator.tests
"""

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from . import store, summarizer
from .judges import (
    ExpectedNote,
    PhraseContext,
    UserNote,
    bar_of,
    beats_per_bar,
    hz_to_cents,
    hz_to_note_name,
    overall_score,
)
from .judges.phase1 import articulation as articulation_judge
from .judges.phase1 import dynamics as dynamics_judge
from .judges.phase1 import notes as notes_judge
from .judges.phase1 import pedaling as pedaling_judge
from .judges.phase1 import pitch as pitch_judge
from .judges.phase1 import rhythm as rhythm_judge
from .judges.phase1 import tempo as tempo_judge
from .judges.phase2 import era as era_judge
from .orchestrator import align_notes, judge_phrase, judge_piece


def expected(note_id=0, hz=440.0, start=0.0, dur=500.0, markings=None):
    return ExpectedNote(
        note_id=note_id, pitch_hz=hz, start_time_ms=start, end_time_ms=start + dur, duration_ms=dur, markings=markings
    )


def user(hz=440.0, start=0.0, dur=500.0, note_id=None):
    return UserNote(pitch_hz=hz, start_time_ms=start, end_time_ms=start + dur, duration_ms=dur, note_id=note_id)


def context(expected_notes, user_notes, bpm=120, time_signature="4/4", phrase=1):
    matched, missing, extra = align_notes(expected_notes, user_notes, bpm)
    return PhraseContext(
        phrase=phrase,
        bpm=bpm,
        beats_per_bar=beats_per_bar(time_signature),
        matched=matched,
        missing=missing,
        extra=extra,
    )


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


class BarNumberingTests(TestCase):
    def test_common_time_signatures_in_quarter_beats(self):
        self.assertEqual(beats_per_bar("4/4"), 4)
        self.assertEqual(beats_per_bar("3/4"), 3)
        self.assertEqual(beats_per_bar("6/8"), 3)

    def test_unparseable_time_signature_falls_back_to_four(self):
        self.assertEqual(beats_per_bar(None), 4)
        self.assertEqual(beats_per_bar("common"), 4)

    def test_bars_are_one_based(self):
        # 120bpm 4/4 -> 500ms beat, 2000ms bar
        self.assertEqual(bar_of(0.0, 120, 4), 1)
        self.assertEqual(bar_of(1999.0, 120, 4), 1)
        self.assertEqual(bar_of(2000.0, 120, 4), 2)


class AlignmentTests(TestCase):
    def test_exact_match(self):
        matched, missing, extra = align_notes([expected(note_id=1)], [user(note_id=1)], bpm=120)
        self.assertEqual(len(matched), 1)
        self.assertEqual(missing, [])
        self.assertEqual(extra, [])

    def test_timing_deviation_within_window_still_matches(self):
        e = [expected(note_id=1, start=1000.0)]
        u = [user(note_id=1, start=1080.0)]  # 80ms late, within window at 120bpm
        self.assertEqual(len(align_notes(e, u, bpm=120)[0]), 1)

    def test_note_outside_window_is_missing_and_extra(self):
        matched, missing, extra = align_notes([expected(note_id=1)], [user(note_id=1, start=5000.0)], bpm=120)
        self.assertEqual(matched, [])
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(extra), 1)

    def test_leftover_user_note_is_extra(self):
        u = [user(note_id=1), user(note_id=2, hz=550.0, start=500.0)]
        matched, _, extra = align_notes([expected(note_id=1)], u, bpm=120)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(extra), 1)

    def test_duplicate_note_id_keeps_longest_duration(self):
        u = [user(note_id=1, dur=100.0), user(note_id=1, dur=480.0)]
        matched, _, extra = align_notes([expected(note_id=1)], u, bpm=120)
        self.assertEqual(matched[0][1].duration_ms, 480.0)
        self.assertEqual(extra, [])

    def test_id_hint_rejected_when_outside_window(self):
        # Same note_id, but way outside the timing window -- must not be
        # blindly trusted; falls back to windowed matching against nothing.
        matched, missing, extra = align_notes([expected(note_id=1)], [user(note_id=1, start=10000.0)], bpm=120)
        self.assertEqual(matched, [])
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(extra), 1)


class PitchJudgeTests(TestCase):
    def test_insignificant_deviation_is_not_a_finding(self):
        result = pitch_judge.judge(context([expected(note_id=1, hz=440.0)], [user(note_id=1, hz=442.0)]))
        self.assertEqual(result.findings, [])  # ~8 cents

    def test_minor_pitch_finding(self):
        result = pitch_judge.judge(context([expected(note_id=1, hz=440.0)], [user(note_id=1, hz=449.0)]))
        self.assertEqual(len(result.findings), 1)  # ~35 cents, inside the 25-50 cent band
        self.assertEqual(result.findings[0].severity, "minor")

    def test_major_wrong_note_names_both_notes(self):
        result = pitch_judge.judge(context([expected(note_id=12, hz=392.0)], [user(note_id=12, hz=369.99)]))
        finding = result.findings[0]
        self.assertEqual(finding.severity, "major")
        self.assertEqual(finding.category, "pitch")
        self.assertIn("F#", finding.message)
        self.assertIn("G", finding.message)
        self.assertEqual(finding.details["note_id"], 12)

    def test_confidence_rises_with_the_error(self):
        small = pitch_judge.judge(context([expected(note_id=1, hz=440.0)], [user(note_id=1, hz=447.0)]))
        large = pitch_judge.judge(context([expected(note_id=1, hz=440.0)], [user(note_id=1, hz=369.99)]))
        self.assertLess(small.findings[0].confidence, large.findings[0].confidence)


class RhythmJudgeTests(TestCase):
    def test_small_offset_at_slow_tempo_is_insignificant(self):
        result = rhythm_judge.judge(context([expected(note_id=1, start=1000.0)], [user(note_id=1, start=1005.0)], bpm=60))
        self.assertEqual(result.findings, [])

    def test_large_offset_is_major(self):
        # 200ms late at 120bpm: past the 125ms major threshold, still inside
        # the 250ms matching window, so it stays a matched note.
        result = rhythm_judge.judge(context([expected(note_id=1, start=1000.0)], [user(note_id=1, start=1200.0)]))
        onset = [f for f in result.findings if f.details["issue"] == "onset"]
        self.assertEqual(onset[0].severity, "major")

    def test_same_offset_judged_differently_at_different_tempo(self):
        e, u = [expected(note_id=1, start=1000.0)], [user(note_id=1, start=1060.0)]  # 60ms
        self.assertEqual(rhythm_judge.judge(context(e, u, bpm=60)).findings, [])
        self.assertTrue(rhythm_judge.judge(context(e, u, bpm=200)).findings)

    def test_small_duration_diff_on_short_note_is_insignificant(self):
        result = rhythm_judge.judge(context([expected(note_id=1, dur=100.0)], [user(note_id=1, dur=110.0)]))
        self.assertEqual(result.findings, [])  # 10ms diff, below the floor

    def test_large_duration_diff_is_major(self):
        result = rhythm_judge.judge(context([expected(note_id=1, dur=500.0)], [user(note_id=1, dur=200.0)]))
        duration = [f for f in result.findings if f.details["issue"] == "duration"]
        self.assertEqual(duration[0].severity, "major")
        self.assertEqual(duration[0].details["direction"], "too_short")


class TempoJudgeTests(TestCase):
    def test_too_few_notes_scores_none(self):
        result = tempo_judge.judge(context([expected(note_id=1)], [user(note_id=1)]))
        self.assertIsNone(result.score)
        self.assertTrue(result.details["insufficient_data"])

    def test_progressive_lateness_is_reported_as_slowing(self):
        e = [expected(note_id=i, start=i * 500.0) for i in range(8)]
        u = [user(note_id=i, start=i * 500.0 + i * 20.0) for i in range(8)]
        result = tempo_judge.judge(context(e, u))
        self.assertEqual(result.findings[0].details["direction"], "slowing")

    def test_steady_offset_is_not_drift(self):
        e = [expected(note_id=i, start=i * 500.0) for i in range(8)]
        u = [user(note_id=i, start=i * 500.0 + 30.0) for i in range(8)]  # uniformly late
        self.assertEqual(tempo_judge.judge(context(e, u)).findings, [])


class NotesJudgeTests(TestCase):
    def test_missing_and_extra_are_major_and_never_scored(self):
        ctx = context([expected(note_id=1)], [user(note_id=1, start=5000.0)])
        result = notes_judge.judge(ctx)
        issues = {f.details["issue"] for f in result.findings}
        self.assertEqual(issues, {"missing_note", "extra_note"})
        self.assertTrue(all(f.severity == "major" for f in result.findings))
        self.assertIsNone(result.score)


class ArticulationJudgeTests(TestCase):
    def test_no_markings_anywhere_scores_none(self):
        self.assertIsNone(articulation_judge.judge(context([expected(note_id=1)], [user(note_id=1)])).score)

    def test_staccato_note_held_too_long_is_flagged(self):
        ctx = context([expected(note_id=1, dur=500.0, markings="staccato")], [user(note_id=1, dur=490.0)])
        result = articulation_judge.judge(ctx)
        self.assertEqual(result.findings[0].category, "articulation")

    def test_staccato_note_played_short_is_fine(self):
        ctx = context([expected(note_id=1, dur=500.0, markings="staccato")], [user(note_id=1, dur=200.0)])
        self.assertEqual(articulation_judge.judge(ctx).findings, [])


class UnavailableJudgeTests(TestCase):
    def test_dynamics_and_pedaling_score_none_and_say_nothing(self):
        ctx = context([expected(note_id=1)], [user(note_id=1)])
        for judge_module in (dynamics_judge, pedaling_judge):
            result = judge_module.judge(ctx)
            self.assertIsNone(result.score)
            self.assertEqual(result.findings, [])
            self.assertIn("unavailable", result.details)


class OverallScoreTests(TestCase):
    def test_renormalizes_over_available_dimensions(self):
        self.assertEqual(overall_score({"pitch": 100, "rhythm": None, "tempo": None}), 100)

    def test_is_none_when_everything_is_none(self):
        self.assertIsNone(overall_score({"pitch": None, "rhythm": None, "notes": None}))

    def test_unweighted_judges_do_not_affect_it(self):
        self.assertEqual(overall_score({"pitch": 100, "notes": 0, "pedaling": 0}), 100)


class JudgePhraseTests(TestCase):
    def _wrong_note_phrase(self):
        return judge_phrase(
            phrase=1,
            bpm=96.0,
            time_signature="4/4",
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

    def test_phase1_file_shape(self):
        result = self._wrong_note_phrase()
        self.assertEqual(result["phrase"], 1)
        self.assertEqual(result["bars"], [1, 1])
        for key in ("overall", "pitch", "rhythm", "tempo", "dynamics", "articulation"):
            self.assertIn(key, result["scores"])
        self.assertIsNone(result["scores"]["dynamics"])

        finding = result["feedback"][0]
        self.assertEqual(
            sorted(finding), sorted(["bars", "category", "severity", "confidence", "message", "details"])
        )
        self.assertEqual(finding["category"], "pitch")
        self.assertEqual(finding["bars"], 1)

    def test_phase1_carries_no_summary(self):
        result = self._wrong_note_phrase()
        for key in ("summary", "phrase_summary", "positive_feedback"):
            self.assertNotIn(key, result)

    def test_findings_are_ordered_by_bar(self):
        expected_notes = [
            {"note_id": i, "pitch_hz": 440.0, "start_time_ms": i * 2000.0,
             "end_time_ms": i * 2000.0 + 500.0, "duration_ms": 500.0}
            for i in range(4)
        ]
        user_notes = [{**note, "pitch_hz": 369.99} for note in expected_notes]
        result = judge_phrase(phrase=1, bpm=120.0, expected_notes=expected_notes, user_notes=user_notes)
        bars = [f["bars"] for f in result["feedback"]]
        self.assertEqual(bars, sorted(bars))
        self.assertEqual(result["bars"], [1, 4])

    def test_missing_required_field_raises_invalid_note_data(self):
        from .errors import InvalidNoteData

        with self.assertRaises(InvalidNoteData):
            judge_phrase(
                phrase=1, bpm=96.0,
                expected_notes=[{"note_id": 1, "pitch_hz": 440.0}],  # missing timing fields
                user_notes=[],
            )

    def test_silence_makes_every_note_missing(self):
        result = judge_phrase(
            phrase=1, bpm=120.0,
            expected_notes=[{"note_id": 1, "pitch_hz": 440.0, "start_time_ms": 0.0, "end_time_ms": 500.0, "duration_ms": 500.0}],
            user_notes=[],
        )
        self.assertEqual(result["feedback"][0]["details"]["issue"], "missing_note")
        self.assertEqual(result["scores"]["pitch"], 0)


class SummarizerTests(TestCase):
    def phrase_file(self, phrase, scores, feedback):
        return {"phrase": phrase, "scores": scores, "feedback": feedback}

    def finding(self, category="pitch", severity="major", issue=None, bars=1):
        details = {"issue": issue} if issue else {}
        return {"bars": bars, "category": category, "severity": severity, "confidence": 1.0,
                "message": "x", "details": details}

    def test_scores_average_across_phrases_and_skip_nulls(self):
        phrases = [
            self.phrase_file(1, {"pitch": 80, "rhythm": None, "tempo": None, "dynamics": None, "articulation": None}, []),
            self.phrase_file(2, {"pitch": 90, "rhythm": None, "tempo": None, "dynamics": None, "articulation": None}, []),
        ]
        scores = summarizer.aggregate_scores(phrases)
        self.assertEqual(scores["pitch"], 85)
        self.assertIsNone(scores["rhythm"])
        self.assertEqual(scores["overall"], 85)

    def test_caps_at_three_and_ranks_major_pitch_above_minor_articulation(self):
        feedback = [self.finding(category="pitch") for _ in range(3)]
        feedback += [self.finding(category="articulation", severity="minor") for _ in range(3)]
        feedback += [self.finding(category="rhythm", severity="minor", issue="onset") for _ in range(2)]
        feedback += [self.finding(category="notes", severity="major", issue="extra_note")]
        main = summarizer.build_main_feedback(feedback)
        self.assertEqual(len(main), 3)
        self.assertEqual(main[0].category, "pitch")

    def test_main_feedback_records_the_bar_span_it_covers(self):
        feedback = [self.finding(bars=2), self.finding(bars=7)]
        self.assertEqual(summarizer.build_main_feedback(feedback)[0].details["bars"], [2, 7])

    def test_empty_when_no_findings(self):
        self.assertEqual(summarizer.build_main_feedback([]), [])

    def test_no_forced_praise_when_nothing_qualifies(self):
        scores = {"pitch": 70, "rhythm": 70, "tempo": 70, "dynamics": None, "articulation": None}
        self.assertEqual(summarizer.build_positive_feedback(scores, []), [])

    def test_high_score_not_flagged_as_a_problem_is_praised(self):
        scores = {"pitch": 95, "rhythm": 95, "tempo": 95, "dynamics": None, "articulation": None}
        self.assertTrue(any("Pitch" in p for p in summarizer.build_positive_feedback(scores, [])))

    def test_praise_is_withheld_for_a_flagged_dimension(self):
        scores = {"pitch": 95, "rhythm": 95, "tempo": None, "dynamics": None, "articulation": None}
        main = summarizer.build_main_feedback([self.finding(category="pitch")])
        self.assertFalse(any("Pitch" in p for p in summarizer.build_positive_feedback(scores, main)))

    def test_summary_line_combines_positive_and_problem_clauses(self):
        main = summarizer.build_main_feedback([self.finding(category="tempo")])
        line = summarizer.build_summary_line(main, ["Pitch accuracy was strong."])
        self.assertIn("strong", line)
        self.assertIn("tempo", line.lower())

    def test_summary_line_when_nothing_to_report(self):
        self.assertIn("No significant issues", summarizer.build_summary_line([], []))


class JudgePieceTests(TestCase):
    def phrases(self):
        return [
            judge_phrase(
                phrase=n, bpm=120.0, time_signature="4/4",
                expected_notes=[{"note_id": 1, "pitch_hz": 392.0, "start_time_ms": 0.0, "end_time_ms": 500.0, "duration_ms": 500.0}],
                user_notes=[{"note_id": 1, "pitch_hz": 369.99, "start_time_ms": 0.0, "end_time_ms": 500.0, "duration_ms": 500.0}],
            )
            for n in (1, 2)
        ]

    def test_produces_one_file_per_phase2_judge_plus_summary(self):
        files = judge_piece(self.phrases(), piece={"title": "Prelude in C", "composed_date": "1722"})
        self.assertEqual(sorted(files), ["Era", "Summary"])

    def test_summary_aggregates_every_phrase(self):
        summary = judge_piece(self.phrases())["Summary"]
        self.assertEqual(summary["phrases"], [1, 2])
        self.assertEqual(summary["feedback"][0]["category"], "pitch")
        self.assertEqual(summary["feedback"][0]["details"]["count"], 2)
        self.assertTrue(summary["summary"])

    def test_era_is_detected_from_the_composition_date(self):
        era = judge_piece(self.phrases(), piece={"composed_date": "1722"})["Era"]
        self.assertEqual(era["era"], "baroque")
        self.assertEqual(era["composed_year"], 1722)
        self.assertEqual(len(era["traits"]), 5)
        self.assertEqual(era["feedback"], [])  # builders not implemented yet

    def test_unknown_date_leaves_the_era_section_empty(self):
        era = judge_piece(self.phrases(), piece={"composed_date": "unknown"})["Era"]
        self.assertIsNone(era["era"])
        self.assertEqual(era["feedback"], [])


class EraDetectionTests(TestCase):
    def test_composed_date_shapes(self):
        cases = {1722: 1722, "1810": 1810, "ca. 1785": 1785, "1830s": 1835,
                 "1802-1804": 1803, "18th century": 1750, None: None, "unknown": None}
        for value, year in cases.items():
            self.assertEqual(era_judge.parse_composed_year(value), year, value)

    def test_era_boundaries_are_inclusive(self):
        self.assertEqual(era_judge.detect_era(1749).era, "baroque")
        self.assertEqual(era_judge.detect_era(1750).era, "classical")
        self.assertEqual(era_judge.detect_era(1819).era, "classical")
        self.assertEqual(era_judge.detect_era(1820).era, "romantic")

    def test_transitional_year_exposes_the_neighbouring_era(self):
        self.assertEqual(era_judge.adjacent_era(1810).era, "romantic")
        self.assertIsNone(era_judge.adjacent_era(1780))


class StoreTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="feedback-store-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def result(self, phrase=1):
        return {"phrase": phrase, "bpm": 96.0, "bars": [1, 1], "scores": {}, "feedback": []}

    def test_session_id_is_date_plus_piece(self):
        session_id = store.session_id_for({"title": "Prelude in C (No. 1)"})
        self.assertTrue(session_id.endswith("-Prelude_in_C_No_1"))

    def test_untitled_piece_still_gets_a_session(self):
        self.assertTrue(store.session_id_for(None).endswith("-Untitled"))

    def test_phrase_goes_to_its_own_phase1_file(self):
        session_id, path = store.save_phrase(self.root, self.result(2), piece={"title": "X"})
        self.assertEqual(path, self.root / "feedback" / session_id / "Phase1" / "Phrase2.json")
        self.assertTrue(path.exists())

    def test_rerecording_a_phrase_overwrites_only_that_file(self):
        session_id, _ = store.save_phrase(self.root, self.result(1))
        store.save_phrase(self.root, self.result(2), session_id=session_id)
        store.save_phrase(self.root, {**self.result(1), "bpm": 60.0}, session_id=session_id)

        phrases = store.load_phrases(self.root, session_id)
        self.assertEqual([entry["phrase"] for entry in phrases], [1, 2])
        self.assertEqual(phrases[0]["bpm"], 60.0)

    def test_piece_metadata_round_trips_for_phase2(self):
        piece = {"title": "Prelude in C", "composer": "Bach", "composed_date": "1722"}
        session_id, _ = store.save_phrase(self.root, self.result(1), piece=piece)
        self.assertEqual(store.load_piece(store.load_phrases(self.root, session_id)), piece)

    def test_phase2_files_land_in_their_own_directory(self):
        session_id, _ = store.save_phrase(self.root, self.result(1))
        written = store.save_phase2(self.root, session_id, {"Summary": {"a": 1}, "Era": {"b": 2}})
        self.assertEqual(written["Era"], self.root / "feedback" / session_id / "Phase2" / "Era.json")
        self.assertTrue(all(path.exists() for path in written.values()))

    def test_path_traversal_session_id_is_rejected(self):
        from .errors import InvalidSessionId

        with self.assertRaises(InvalidSessionId):
            store.save_phrase(self.root, self.result(1), session_id="../../etc/passwd")
        with self.assertRaises(InvalidSessionId):
            store.phase2_path(self.root, "2026-01-01-X", "../Era")
