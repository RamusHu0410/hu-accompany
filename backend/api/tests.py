import json

from django.test import TestCase


class PhraseFeedbackViewTests(TestCase):
    url = "/api/feedback/phrase"

    valid_body = {
        "phrase": 0,
        "timing": {"bpm": 96.0, "time_signature": "4/4"},
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

    def _post(self, body):
        return self.client.post(self.url, data=json.dumps(body), content_type="application/json")

    def test_valid_payload_returns_200_with_expected_shape(self):
        response = self._post(self.valid_body)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["phrase"], 0)
        self.assertIn("immediate_feedback", data)
        self.assertIn("phrase_summary", data)
        self.assertIn("scores", data["phrase_summary"])

    def test_invalid_json_returns_400(self):
        response = self.client.post(self.url, data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "invalid JSON"})

    def test_missing_expected_notes_returns_400(self):
        body = {**self.valid_body, "expected_notes": []}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)

    def test_non_positive_bpm_returns_400(self):
        body = {**self.valid_body, "timing": {"bpm": 0}}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)

    def test_malformed_note_returns_400_not_500(self):
        body = {**self.valid_body, "expected_notes": [{"note_id": 1, "pitch_hz": 440.0}]}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
