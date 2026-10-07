"""The hum app's HTTP layer: upload, both engines, the notes graph, and talk mode with fake Gemini and
ElevenLabs. The engines themselves are tested by the pytest suites next to this file.

Run with `python manage.py test hum`. Songs are rendered with FluidSynth, so those tests skip on a
machine without it or a soundfont.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from hum import paths, talk_views
from hum.engine.accompanist.audio.render import find_soundfont
from hum.engine.talk.commands import Command
from hum.tests.talk.talk_fakes import FakeEars, FakeGemini, fake_services, write_hum

HUM_SAMPLE = Path(__file__).parent / "fixtures" / "hum_sample.wav"


def can_render() -> bool:
    try:
        find_soundfont()
    except FileNotFoundError:
        return False
    return shutil.which("fluidsynth") is not None


class HumTestCase(SimpleTestCase):
    """Each test gets its own empty hum_data folder."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="hum-test-"))
        override = override_settings(HUM_DATA_DIR=self.data)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.data, ignore_errors=True)

    def upload(self, source=HUM_SAMPLE, name="hum.wav"):
        with open(source, "rb") as file:
            return self.client.post("/api/hum/upload", {"file": _named(file, name)})

    def post_json(self, url, body):
        return self.client.post(url, json.dumps(body), content_type="application/json")

    def uploaded_hum(self) -> str:
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["filename"]


def _named(file, name):
    return SimpleUploadedFile(name, file.read(), content_type="audio/wav")


class UploadTests(HumTestCase):
    def test_finds_the_tune_in_a_hum(self):
        body = self.upload().json()
        self.assertGreater(len(body["melody"]), 2)
        self.assertEqual(set(body["melody"][0]), {"hz", "start", "duration"})
        self.assertIn(body["mode"], ("major", "minor"))
        self.assertGreater(body["tempo"], 0)
        self.assertTrue((self.data / "uploads" / body["filename"]).is_file())

    def test_each_upload_gets_its_own_name(self):
        self.assertNotEqual(self.upload().json()["filename"], self.upload().json()["filename"])

    def test_refuses_what_is_not_a_wav(self):
        self.assertEqual(self.client.post("/api/hum/upload").status_code, 400)
        response = self.client.post("/api/hum/upload", {"file": _named(io.BytesIO(b"hi"), "notes.txt")})
        self.assertEqual(response.status_code, 400)

    def test_refuses_a_broken_wav_and_keeps_nothing(self):
        response = self.client.post("/api/hum/upload", {"file": _named(io.BytesIO(b"not really audio"), "hum.wav")})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        self.assertEqual(list((self.data / "uploads").iterdir()), [])

    def test_refuses_silence_with_a_reason_the_user_can_act_on(self):
        silent = self.data / "silent.wav"
        with wave.open(str(silent), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(22050)
            out.writeframes(b"\x00\x00" * 22050)
        response = self.upload(silent)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "silent")

    def test_only_post(self):
        self.assertEqual(self.client.get("/api/hum/upload").status_code, 405)


class SavedHumTests(HumTestCase):
    def test_a_name_cannot_leave_the_uploads_folder(self):
        (self.data / "secret.txt").write_text("x")
        self.assertIsNone(paths.saved_hum("../secret.txt"))
        self.assertIsNone(paths.saved_hum("/etc/passwd"))

    def test_a_saved_hum_is_found(self):
        name = self.uploaded_hum()
        self.assertEqual(paths.saved_hum(name).name, name)


class RequestErrorTests(HumTestCase):
    def test_bad_requests(self):
        for url in ("/api/hum/song", "/api/hum/notes"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, "{not json", content_type="application/json").status_code, 400)
                self.assertEqual(self.post_json(url, {}).status_code, 400)
                self.assertEqual(self.post_json(url, {"hum": "gone.wav"}).status_code, 404)
                self.assertEqual(self.post_json(url, {"hum": "../../etc/passwd"}).status_code, 404)

    def test_unknown_engine(self):
        response = self.post_json("/api/hum/song", {"hum": self.uploaded_hum(), "engine": "loud"})
        self.assertEqual(response.status_code, 400)

    def test_unusable_settings(self):
        hum = self.uploaded_hum()
        for engine in ("epic", "simple"):
            with self.subTest(engine=engine):
                response = self.post_json("/api/hum/song", {"hum": hum, "engine": engine, "settings": {"speed": "fast"}})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "bad_settings")


@unittest.skipUnless(can_render(), "needs FluidSynth and a soundfont")
class SongTests(HumTestCase):
    def test_both_engines_make_a_wav(self):
        hum = self.uploaded_hum()
        for engine in ("epic", "simple"):
            with self.subTest(engine=engine):
                response = self.post_json("/api/hum/song", {"hum": hum, "engine": engine})
                self.assertEqual(response.status_code, 200, response.content[:200])
                self.assertEqual(response["Content-Type"], "audio/wav")
                with wave.open(io.BytesIO(response.content)) as song:
                    self.assertGreater(song.getnframes() / song.getframerate(), 2)

    def test_epic_is_the_default_engine(self):
        hum = self.uploaded_hum()
        default = self.post_json("/api/hum/song", {"hum": hum}).content
        epic = self.post_json("/api/hum/song", {"hum": hum, "engine": "epic"}).content
        simple = self.post_json("/api/hum/song", {"hum": hum, "engine": "simple"}).content
        self.assertEqual(len(default), len(epic))
        self.assertNotEqual(len(default), len(simple))

    def test_settings_change_the_song(self):
        hum = self.uploaded_hum()
        for engine in ("epic", "simple"):
            with self.subTest(engine=engine):
                slow = self.post_json("/api/hum/song", {"hum": hum, "engine": engine, "settings": {"speed": 0.0}}).content
                fast = self.post_json("/api/hum/song", {"hum": hum, "engine": engine, "settings": {"speed": 1.0}}).content
                self.assertGreater(len(slow), len(fast))


class NotesTests(HumTestCase):
    def test_both_engines_give_what_the_graph_draws(self):
        hum = self.uploaded_hum()
        for engine in ("epic", "simple"):
            with self.subTest(engine=engine):
                response = self.post_json("/api/hum/notes", {"hum": hum, "engine": engine})
                self.assertEqual(response.status_code, 200, response.content[:200])
                body = response.json()
                self.assertEqual(set(body), {"sung", "played", "contour"})
                self.assertGreater(len(body["sung"]), 0)
                self.assertEqual(set(body["sung"][0]), {"midi", "start", "duration"})


class EnginesTests(HumTestCase):
    def test_lists_both_engines_with_their_styles(self):
        body = self.client.get("/api/hum/engines").json()
        engines = {engine["id"]: engine for engine in body["engines"]}
        self.assertEqual(set(engines), {"epic", "simple"})
        self.assertIn("cinematic", engines["epic"]["styles"])
        self.assertIn("jazz", engines["simple"]["styles"])
        self.assertEqual(body["default"], "epic")


class TalkTests(HumTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(talk_views.reset_services)

    def use(self, **fakes):
        talk_views.reset_services(fake_services(**fakes))

    def test_typed_command_changes_the_settings(self):
        self.use()
        response = self.post_json("/api/hum/talk", {"text": "make it faster", "settings": {"speed": 0.5}})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "adjust")
        self.assertAlmostEqual(body["settings"]["speed"], 0.7)
        self.assertEqual(body["changed"], ["speed"])
        self.assertTrue(body["reply"])
        self.assertTrue(body["speech_id"])

    def test_spoken_command_is_heard_first(self):
        self.use(ears=FakeEars("make it faster"))
        response = self.client.post(
            "/api/hum/talk",
            {"audio": _named(io.BytesIO(b"fake audio"), "talk.wav"), "state": json.dumps({"settings": {"speed": 0.5}})},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["heard"], "make it faster")

    def test_undo_goes_back_to_the_previous_settings(self):
        self.use(gemini=FakeGemini(Command(intent="undo", reply="Back it goes.")))
        response = self.post_json(
            "/api/hum/talk", {"text": "undo", "settings": {"speed": 0.7}, "previous": {"speed": 0.5}}
        )
        self.assertAlmostEqual(response.json()["settings"]["speed"], 0.5)

    def test_a_failing_service_leaves_the_settings_alone(self):
        self.use(gemini=FakeGemini(error=RuntimeError("quota")))
        response = self.post_json("/api/hum/talk", {"text": "faster", "settings": {"speed": 0.5}})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "error")
        self.assertEqual(body["settings"]["speed"], 0.5)

    def test_bad_requests(self):
        self.use()
        self.assertEqual(self.post_json("/api/hum/talk", {}).status_code, 400)
        self.assertEqual(self.post_json("/api/hum/talk", {"text": "hi", "settings": {"speed": "x"}}).status_code, 400)
        self.assertEqual(self.client.post("/api/hum/talk", "nope", content_type="application/json").status_code, 400)

    def test_reply_is_spoken_as_streamed_mp3(self):
        self.use()
        speech_id = self.post_json("/api/hum/talk", {"text": "faster"}).json()["speech_id"]
        response = self.client.get(f"/api/hum/talk/speech/{speech_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(b"".join(response.streaming_content), b"ID3-first-chunk-rest-of-the-mp3")

    def test_an_unknown_reply_is_expired(self):
        self.use()
        self.assertEqual(self.client.get("/api/hum/talk/speech/nope").status_code, 404)

    def test_a_missing_key_is_said_plainly(self):
        with _no_keys():
            talk_views.reset_services()
            response = self.post_json("/api/hum/talk", {"text": "faster"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "error")
        self.assertEqual(body["settings"]["speed"], 0.5)


class _no_keys:
    """Runs a block as if no API keys were set."""

    def __enter__(self):
        self._saved = {key: os.environ.pop(key, None) for key in ("GEMINI_API_KEY", "ELEVENLABS_API_KEY")}

    def __exit__(self, *exc):
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value
