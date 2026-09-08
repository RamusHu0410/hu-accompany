import json
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


# Feedback is persisted under STORAGE_ROOT/feedback (see
# feedback_generator/store.py), so tests point STORAGE_ROOT at a temp
# directory rather than writing into the real backend/storage tree.
class FeedbackViewTestCase(TestCase):
    valid_body = {
        "phrase": 1,
        "timing": {"bpm": 96.0, "time_signature": "4/4"},
        "piece": {"title": "Prelude in C", "composer": "Bach", "composed_date": "1722"},
        "expected_notes": [
            {
                "note_id": 12, "pitch_hz": 392.0, "start_time_ms": 1000.0,
                "end_time_ms": 1500.0, "duration_ms": 500.0,
                "vibrato_depth": None, "pedal_action": None, "has_accent": None, "markings": None,
            }
        ],
        "user_notes": [
            {"note_id": 12, "pitch_hz": 392.0, "start_time_ms": 1000.0, "end_time_ms": 1500.0, "duration_ms": 500.0}
        ],
    }

    def setUp(self):
        self.storage_root = Path(tempfile.mkdtemp(prefix="feedback-store-test-"))
        self.addCleanup(shutil.rmtree, self.storage_root, ignore_errors=True)
        override = override_settings(STORAGE_ROOT=self.storage_root)
        override.enable()
        self.addCleanup(override.disable)

    def _post(self, url, body):
        return self.client.post(url, data=json.dumps(body), content_type="application/json")

    def _post_phrase(self, body=None):
        return self._post("/api/feedback/phrase", body or self.valid_body)

    def _sessions(self):
        return sorted(child.name for child in (self.storage_root / "feedback").glob("*") if child.is_dir())

    def _phase1_files(self):
        return sorted((self.storage_root / "feedback").glob("*/Phase1/*.json"))

    def _phase2_files(self):
        return sorted((self.storage_root / "feedback").glob("*/Phase2/*.json"))


class PhraseFeedbackViewTests(FeedbackViewTestCase):
    url = "/api/feedback/phrase"

    def test_valid_payload_returns_200_with_phase1_shape(self):
        response = self._post_phrase()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["phrase"], 1)
        self.assertIn("feedback", data)
        self.assertIn("bars", data)
        self.assertIn("scores", data)
        self.assertNotIn("summary", data)  # summaries are phase 2

    def test_invalid_json_returns_400(self):
        response = self.client.post(self.url, data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "invalid JSON"})

    def test_missing_expected_notes_returns_400(self):
        self.assertEqual(self._post_phrase({**self.valid_body, "expected_notes": []}).status_code, 400)

    def test_non_positive_bpm_returns_400(self):
        self.assertEqual(self._post_phrase({**self.valid_body, "timing": {"bpm": 0}}).status_code, 400)

    def test_phrase_below_one_returns_400(self):
        self.assertEqual(self._post_phrase({**self.valid_body, "phrase": 0}).status_code, 400)

    def test_malformed_note_returns_400_not_500(self):
        body = {**self.valid_body, "expected_notes": [{"note_id": 1, "pitch_hz": 440.0}]}
        self.assertEqual(self._post_phrase(body).status_code, 400)

    def test_result_is_written_to_a_dated_piece_directory(self):
        data = self._post_phrase().json()

        self.assertTrue(data["session_id"].endswith("-Prelude_in_C"))
        self.assertIsNone(data.get("storage_error"))
        self.assertTrue(data["stored_at"].endswith("/Phase1/Phrase1.json"))

        files = self._phase1_files()
        self.assertEqual(len(files), 1)
        stored = json.loads(files[0].read_text())
        self.assertEqual(stored["phrase"], 1)
        self.assertEqual(stored["bpm"], 96.0)
        self.assertEqual(stored["piece"], self.valid_body["piece"])

    def test_each_phrase_gets_its_own_file_in_one_session(self):
        first = self._post_phrase().json()
        self._post_phrase({**self.valid_body, "phrase": 2, "session_id": first["session_id"]})
        self._post_phrase({**self.valid_body, "session_id": first["session_id"]})  # retake of phrase 1

        self.assertEqual(len(self._sessions()), 1)
        self.assertEqual([p.name for p in self._phase1_files()], ["Phrase1.json", "Phrase2.json"])

    def test_a_different_piece_gets_its_own_session(self):
        self._post_phrase()
        self._post_phrase({**self.valid_body, "piece": {"title": "Fugue in D"}})
        self.assertEqual(len(self._sessions()), 2)

    def test_path_traversal_session_id_returns_400(self):
        response = self._post_phrase({**self.valid_body, "session_id": "../../etc/passwd"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._phase1_files(), [])


class SummaryFeedbackViewTests(FeedbackViewTestCase):
    url = "/api/feedback/summary"

    def _session_with_two_phrases(self):
        wrong_note = [
            {"note_id": 12, "pitch_hz": 369.99, "start_time_ms": 1000.0, "end_time_ms": 1500.0, "duration_ms": 500.0}
        ]
        first = self._post_phrase({**self.valid_body, "user_notes": wrong_note}).json()
        self._post_phrase({**self.valid_body, "phrase": 2, "session_id": first["session_id"], "user_notes": wrong_note})
        return first["session_id"]

    def test_summarizes_every_stored_phrase_into_phase2(self):
        session_id = self._session_with_two_phrases()
        data = self._post(self.url, {"session_id": session_id}).json()

        self.assertEqual(data["phrases"], [1, 2])
        self.assertEqual(sorted(data["phase2"]), ["Era", "Summary"])
        self.assertEqual(data["phase2"]["Summary"]["feedback"][0]["category"], "pitch")
        self.assertTrue(data["phase2"]["Summary"]["summary"])
        self.assertEqual([p.name for p in self._phase2_files()], ["Era.json", "Summary.json"])

    def test_era_comes_from_the_piece_metadata_stored_in_phase1(self):
        session_id = self._session_with_two_phrases()
        data = self._post(self.url, {"session_id": session_id}).json()
        self.assertEqual(data["phase2"]["Era"]["era"], "baroque")

    def test_rerunning_overwrites_phase2(self):
        session_id = self._session_with_two_phrases()
        self._post(self.url, {"session_id": session_id})
        self._post(self.url, {"session_id": session_id})
        self.assertEqual(len(self._phase2_files()), 2)

    def test_unknown_session_returns_404(self):
        response = self._post(self.url, {"session_id": "2026-01-01-Nothing"})
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_session_id_returns_400(self):
        self.assertEqual(self._post(self.url, {"session_id": "../../etc"}).status_code, 400)

    def test_invalid_json_returns_400(self):
        response = self.client.post(self.url, data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
