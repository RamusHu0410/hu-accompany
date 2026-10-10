"""The chat and project-edit endpoints (hum/views_chat.py), with Gemini and ElevenLabs faked.
Runs under `python manage.py test hum`."""

import json

from django.core.files.uploadedfile import SimpleUploadedFile

from hum import views_chat
from hum.chat.commands import Answer
from hum.chat.interpreter import GeminiBusy
from hum.chat.services import build_chat_services
from hum.engine.talk.config import Config
from hum.tests.chat.chat_fakes import FakeEars, FakeGemini, fake_chat_services
from hum.tests.test_api import HumTestCase


class ChatTests(HumTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(views_chat.reset_services)
        hum = self.uploaded_hum()
        self.project = self.post_json("/api/hum/project", {"hum": hum, "settings": {"style": "lofi"}}).json()["project"]

    def use(self, **fakes):
        views_chat.reset_services(fake_chat_services(**fakes))

    def test_a_typed_message_edits_the_project(self):
        self.use()
        body = self.post_json("/api/hum/chat", {"text": "softer drums", "project": self.project}).json()
        self.assertEqual(body["intent"], "edit")
        self.assertEqual(body["reply"], "Drums are softer now.")
        self.assertEqual((body["changed"], body["mixed"], body["label"]), ([], ["drums"], "drums quieter"))
        drums = next(t for t in body["project"]["tracks"] if t["role"] == "drums")
        before = next(t for t in self.project["tracks"] if t["role"] == "drums")
        self.assertLess(drums["volume"], before["volume"])
        self.assertTrue(body["speech_id"])

    def test_a_spoken_message_is_heard_then_edits(self):
        ears = FakeEars("quieter drums")
        self.use(ears=ears)
        response = self.client.post("/api/hum/chat", {
            "audio": SimpleUploadedFile("talk.wav", b"RIFF....", content_type="audio/wav"),
            "state": json.dumps({"project": self.project, "can_undo": False}),
        })
        body = response.json()
        self.assertEqual(body["heard"], "quieter drums")
        self.assertIsNotNone(body["project"])
        self.assertEqual(ears.calls[0][1], "talk.wav")

    def test_the_reply_is_spoken_as_streamed_mp3(self):
        self.use()
        speech_id = self.post_json("/api/hum/chat", {"text": "softer drums", "project": self.project}).json()["speech_id"]
        response = self.client.get(f"/api/hum/chat/speech/{speech_id}")
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(b"".join(response.streaming_content), b"ID3-first-chunk-rest-of-the-mp3")
        self.assertEqual(self.client.get("/api/hum/chat/speech/nope").status_code, 404)

    def test_a_voice_that_fails_says_so_and_the_text_still_stands(self):
        def broken(_text):
            raise RuntimeError("quota")

        self.use(speak=broken)
        turn = self.post_json("/api/hum/chat", {"text": "softer drums", "project": self.project}).json()
        self.assertEqual(turn["intent"], "edit")
        response = self.client.get(f"/api/hum/chat/speech/{turn['speech_id']}")
        self.assertEqual((response.status_code, response.json()["code"]), (503, "voice_unavailable"))

    def test_a_busy_gemini_leaves_the_song_alone(self):
        self.use(gemini=FakeGemini(error=GeminiBusy("429")))
        body = self.post_json("/api/hum/chat", {"text": "faster", "project": self.project}).json()
        self.assertEqual(body["intent"], "busy")
        self.assertIsNone(body["project"])

    def test_undo_is_the_apps_to_do(self):
        self.use(gemini=FakeGemini(Answer(intent="undo", language="English", reply="Back it goes.")))
        body = self.post_json("/api/hum/chat", {"text": "undo", "project": self.project, "can_undo": False}).json()
        self.assertEqual(body["intent"], "undo")
        self.assertEqual(body["reply"], "There's nothing to undo yet.")

    def test_a_missing_key_is_said_plainly(self):
        no_keys = Config("", "", "model", "minimal", "voice", "tts", "stt")
        views_chat.reset_services(build_chat_services(no_keys))
        body = self.post_json("/api/hum/chat", {"text": "faster", "project": self.project}).json()
        self.assertEqual(body["intent"], "error")
        self.assertIn("GEMINI_API_KEY is missing", body["reply"])
        speech = self.client.get(f"/api/hum/chat/speech/{body['speech_id']}")
        self.assertEqual(speech.status_code, 503)

    def test_bad_requests(self):
        self.use()
        self.assertEqual(self.post_json("/api/hum/chat", {"text": "hi"}).status_code, 400)
        self.assertEqual(self.post_json("/api/hum/chat", {"project": self.project}).status_code, 400)
        broken = self.post_json("/api/hum/chat", {"text": "hi", "project": {"version": 7}})
        self.assertEqual(broken.json()["code"], "bad_project")
        self.assertEqual(self.client.get("/api/hum/chat").status_code, 405)


class ProjectEditTests(HumTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.post_json("/api/hum/project", {"hum": self.uploaded_hum()}).json()["project"]

    def test_edits_apply_without_gemini(self):
        body = self.post_json("/api/hum/project/edit", {"project": self.project, "edits": [
            {"action": "set_genre", "genre": "jazz"}, {"action": "mute", "part": "drums"}]}).json()
        self.assertEqual(body["project"]["preset"], "jazz")
        self.assertTrue(next(t for t in body["project"]["tracks"] if t["role"] == "drums")["mute"])
        self.assertEqual(body["label"], "jazz now, drums muted")
        self.assertEqual(body["refused"], [])

    def test_unknown_edits_are_refused(self):
        response = self.post_json("/api/hum/project/edit", {"project": self.project, "edits": [{"action": "explode"}]})
        self.assertEqual(response.json()["code"], "bad_edits")
        too_many = [{"action": "mute", "part": "drums"}] * 5
        self.assertEqual(self.post_json("/api/hum/project/edit", {"project": self.project, "edits": too_many}).status_code, 400)

    def test_the_graph_follows_the_edited_song(self):
        edited = self.post_json("/api/hum/project/edit", {"project": self.project, "edits": [
            {"action": "transpose", "value": 2}]}).json()["project"]
        before = self.post_json("/api/hum/project/notes", {"project": self.project}).json()
        after = self.post_json("/api/hum/project/notes", {"project": edited}).json()
        self.assertEqual(before["sung"], after["sung"])  # what was hummed doesn't change
        self.assertEqual([n["midi"] + 2 for n in before["played"]], [n["midi"] for n in after["played"]])
        gone = self.post_json("/api/hum/project/notes", {"project": {**self.project, "hum": "gone.wav"}})
        self.assertEqual(gone.status_code, 404)
