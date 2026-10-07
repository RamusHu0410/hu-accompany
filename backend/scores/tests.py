import json
import shutil
import sqlite3
import tempfile
import zipfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from scores import catalog
from scores.models import Score
from scores.musicxml import InvalidMusicXML, inspect, read_musicxml

SCORE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <direction><sound tempo="72"/></direction>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>3</duration></note>
    </measure>
    <measure number="2">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>3</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def write_mxl(path: Path, xml: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>',
        )
        z.writestr("score.xml", xml)


class MusicXMLTests(SimpleTestCase):
    def test_reads_facts(self):
        facts = inspect(SCORE_XML)
        self.assertEqual(facts.part_count, 1)
        self.assertEqual(facts.measure_count, 2)
        self.assertEqual(facts.time_signature, "3/4")
        self.assertEqual(facts.tempo_bpm, 72.0)

    def test_rejects_broken_scores(self):
        for xml in (
            b"<score-partwise",
            b"<score-timewise/>",
            b"<score-partwise><part id='P1'/></score-partwise>",
            b"<score-partwise><part id='P1'><measure/></part></score-partwise>",
        ):
            with self.subTest(xml=xml), self.assertRaises(InvalidMusicXML):
                inspect(xml)

    def test_unzips_mxl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.mxl"
            write_mxl(path, SCORE_XML)
            self.assertEqual(read_musicxml(path), SCORE_XML)

    def test_repairs_mojibake_but_keeps_real_names(self):
        self.assertEqual(catalog.clean_text("FrÃ©dÃ©ric  Chopin"), "Frédéric Chopin")
        self.assertEqual(catalog.clean_text("Håkan Hardenberger"), "Håkan Hardenberger")


class ImportCommandTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdmx-test-"))
        self.storage = self.root / "storage"
        self.catalog = self.root / "pdmx.db"
        rows = [
            # title, composer, mxl, rating, is_deduplicated
            ("Nocturne", "FrÃ©dÃ©ric Chopin", "./mxl/0/1/good.mxl", 4.9, 1),
            ("Copy", "Chopin", "./mxl/0/1/copy.mxl", 4.8, 1),
            ("Broken", "Bach", "./mxl/0/1/broken.mxl", 4.7, 1),
            ("Missing", "Bach", "./mxl/0/1/missing.mxl", 4.6, 1),
            ("No composer", "NA", "./mxl/0/1/nc.mxl", 4.9, 1),
            ("Low rated", "Bach", "./mxl/0/1/low.mxl", 1.0, 1),
        ]
        with sqlite3.connect(self.catalog) as conn:
            conn.execute(
                "CREATE TABLE pieces (title, song_name, artist_name, composer_name,"
                " mxl, path, rating, is_deduplicated)"
            )
            conn.executemany(
                "INSERT INTO pieces VALUES (?, '', '', ?, ?, '', ?, ?)", rows
            )
        write_mxl(self.root / "mxl/0/1/good.mxl", SCORE_XML)
        write_mxl(self.root / "mxl/0/1/copy.mxl", SCORE_XML)
        write_mxl(self.root / "mxl/0/1/broken.mxl", b"<score-partwise")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_import(self):
        out = StringIO()
        with override_settings(STORAGE_ROOT=self.storage):
            call_command(
                "import_pdmx", pdmx_root=self.root, catalog=self.catalog, stdout=out
            )
        return out.getvalue()

    def test_imports_valid_scores_and_reports_the_rest(self):
        output = self.run_import()

        score = Score.objects.get()
        self.assertEqual(score.composer, "Frédéric Chopin")
        self.assertEqual(score.pdmx_path, "mxl/0/1/good.mxl")
        self.assertEqual((self.storage / score.musicxml_path).read_bytes(), SCORE_XML)
        self.assertIn("imported: 1", output)

        report = json.loads((self.storage / "musicxml/import_report.json").read_text())
        reasons = {entry["title"]: entry["reason"] for entry in report}
        self.assertEqual(reasons["Copy"], "duplicate content")
        self.assertTrue(reasons["Broken"].startswith("invalid"))
        self.assertEqual(reasons["Missing"], "missing file")
        self.assertNotIn("No composer", reasons)
        self.assertNotIn("Low rated", reasons)

    def test_rerun_skips_existing_rows(self):
        self.run_import()
        self.assertIn("already imported: 1", self.run_import())
        self.assertEqual(Score.objects.count(), 1)


class ScoreViewTests(TestCase):
    def setUp(self):
        self.storage = Path(tempfile.mkdtemp(prefix="scores-view-test-"))
        (self.storage / "musicxml").mkdir()
        (self.storage / "musicxml/a.musicxml").write_bytes(SCORE_XML)
        self.score = Score.objects.create(
            title="Nocturne Op.9 No.2", composer="Frédéric Chopin", rating=4.9,
            pdmx_path="mxl/a.mxl", musicxml_path="musicxml/a.musicxml", sha256="a",
            part_count=1, measure_count=2, time_signature="3/4", tempo_bpm=72,
        )
        Score.objects.create(
            title="Prelude in C", composer="J. S. Bach", rating=4.5,
            pdmx_path="mxl/b.mxl", musicxml_path="musicxml/b.musicxml", sha256="b",
            part_count=1, measure_count=1,
        )

    def tearDown(self):
        shutil.rmtree(self.storage, ignore_errors=True)

    def test_search_matches_every_word_across_title_and_composer(self):
        response = self.client.get("/api/scores/search", {"q": "chopin nocturne"})
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([r["id"] for r in results], [self.score.id])
        self.assertEqual(results[0]["time_signature"], "3/4")

    def test_search_requires_a_query(self):
        self.assertEqual(self.client.get("/api/scores/search").status_code, 400)

    def test_serves_musicxml(self):
        with override_settings(STORAGE_ROOT=self.storage):
            response = self.client.get(f"/api/scores/{self.score.id}/musicxml")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), SCORE_XML)

    def test_missing_score_or_file_is_404(self):
        with override_settings(STORAGE_ROOT=self.storage):
            self.assertEqual(self.client.get("/api/scores/999/musicxml").status_code, 404)
            missing = Score.objects.get(sha256="b")
            self.assertEqual(
                self.client.get(f"/api/scores/{missing.id}/musicxml").status_code, 404
            )
