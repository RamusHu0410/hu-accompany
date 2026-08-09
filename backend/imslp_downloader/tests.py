"""Console test:
cd backend
python manage.py download_score "imslp-url"
"""


import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.models import Version, Work

from . import downloader
from .browser import DownloadedFile
from .exceptions import (
    BrowserError,
    DownloadFailed,
    FileSaveFailed,
    InvalidIMSLPURL,
    SubscriptionRequired,
)
from .models import Download, DownloadStatus


def _mock_browser_cls(downloaded_file=None, enter_side_effect=None, download_file_side_effect=None):
    """Build a mock IMSLPBrowser class matching `with IMSLPBrowser() as browser: ...`."""
    instance = MagicMock()
    if download_file_side_effect is not None:
        instance.download_file.side_effect = download_file_side_effect
    else:
        instance.download_file.return_value = downloaded_file

    browser_cls = MagicMock()
    if enter_side_effect is not None:
        browser_cls.return_value.__enter__.side_effect = enter_side_effect
    else:
        browser_cls.return_value.__enter__.return_value = instance
    browser_cls.return_value.__exit__.return_value = False
    return browser_cls


class ValidateUrlTests(TestCase):
    def test_rejects_non_imslp_domain(self):
        with self.assertRaises(InvalidIMSLPURL):
            downloader.download("no-such-score", "https://example.com/file.pdf")

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(InvalidIMSLPURL):
            downloader.download("no-such-score", "ftp://imslp.org/file.pdf")

    def test_rejects_empty_url(self):
        with self.assertRaises(InvalidIMSLPURL):
            downloader.download("no-such-score", "")

    def test_invalid_url_does_not_create_a_download_record(self):
        with self.assertRaises(InvalidIMSLPURL):
            downloader.download("no-such-score", "https://example.com/file.pdf")
        self.assertEqual(Download.objects.count(), 0)


class FindExistingTests(TestCase):
    def test_returns_none_when_no_download_exists(self):
        self.assertIsNone(downloader.find_existing("abc"))

    def test_ignores_non_completed_download(self):
        Download.objects.create(
            score_id_raw="abc", imslp_url="https://imslp.org/x", status=DownloadStatus.FAILED
        )
        self.assertIsNone(downloader.find_existing("abc"))

    def test_returns_none_when_file_missing_on_disk(self):
        Download.objects.create(
            score_id_raw="abc",
            imslp_url="https://imslp.org/x",
            status=DownloadStatus.COMPLETED,
            file_path="storage/scores/missing.pdf",
        )
        with patch.object(downloader.storage, "exists", return_value=False):
            self.assertIsNone(downloader.find_existing("abc"))

    def test_returns_download_when_completed_and_file_exists(self):
        record = Download.objects.create(
            score_id_raw="abc",
            imslp_url="https://imslp.org/x",
            status=DownloadStatus.COMPLETED,
            file_path="storage/scores/x.pdf",
        )
        with patch.object(downloader.storage, "exists", return_value=True):
            found = downloader.find_existing("abc")
        self.assertEqual(found.pk, record.pk)


class DownloadTests(TestCase):
    def setUp(self):
        self.work = Work.objects.create(
            title="Piano Sonata No. 14",
            composer="Beethoven, Ludwig van",
            imslp_url="https://imslp.org/wiki/Work",
        )
        self.version = Version.objects.create(
            work=self.work,
            name="Piano solo",
            type="score",
            imslp_url="https://imslp.org/wiki/file.pdf",
        )

    def test_successful_download_creates_completed_record(self):
        downloaded = DownloadedFile(
            tmp_path="/tmp/fake.pdf", suggested_filename="fake.pdf", source_url=self.version.imslp_url
        )
        with patch(
            "imslp_downloader.downloader.IMSLPBrowser", _mock_browser_cls(downloaded)
        ), patch.object(
            downloader.storage, "build_relative_path", return_value=Path("scores/Beethoven/Piano_Sonata/Piano_solo.pdf")
        ), patch.object(
            downloader.storage, "save", return_value=12345
        ), patch.object(
            downloader.storage, "validate_pdf"
        ), patch.object(
            downloader.storage,
            "to_db_path",
            return_value="storage/scores/Beethoven/Piano_Sonata/Piano_solo.pdf",
        ), patch(
            "imslp_downloader.downloader.os.remove"
        ):
            record = downloader.download(str(self.version.id), self.version.imslp_url)

        self.assertEqual(record.status, DownloadStatus.COMPLETED)
        self.assertEqual(record.file_size, 12345)
        self.assertEqual(record.file_path, "storage/scores/Beethoven/Piano_Sonata/Piano_solo.pdf")
        self.assertIsNone(record.error_message)
        self.assertEqual(Download.objects.count(), 1)

    def test_falls_back_to_client_url_when_score_not_found(self):
        downloaded = DownloadedFile(
            tmp_path="/tmp/fake.pdf", suggested_filename="other.pdf", source_url="https://imslp.org/wiki/other.pdf"
        )
        with patch(
            "imslp_downloader.downloader.IMSLPBrowser", _mock_browser_cls(downloaded)
        ), patch.object(
            downloader.storage, "build_relative_path", return_value=Path("scores/Unknown/Untitled_Work/other.pdf")
        ), patch.object(
            downloader.storage, "save", return_value=1
        ), patch.object(
            downloader.storage, "validate_pdf"
        ), patch.object(
            downloader.storage, "to_db_path", return_value="storage/scores/Unknown/Untitled_Work/other.pdf"
        ), patch(
            "imslp_downloader.downloader.os.remove"
        ):
            record = downloader.download("nonexistent-id", "https://imslp.org/wiki/other.pdf")

        self.assertIsNone(record.score)
        self.assertEqual(record.imslp_url, "https://imslp.org/wiki/other.pdf")

    def test_falls_back_to_client_url_does_not_double_extension(self):
        downloaded = DownloadedFile(
            tmp_path="/tmp/fake.pdf",
            suggested_filename="IMSLP37119-PMLP01969-Chopin_Op.10_600dpi.pdf",
            source_url="https://imslp.org/wiki/other.pdf",
        )
        with patch(
            "imslp_downloader.downloader.IMSLPBrowser", _mock_browser_cls(downloaded)
        ), patch.object(
            downloader.storage, "save", return_value=1
        ), patch.object(
            downloader.storage, "validate_pdf"
        ), patch(
            "imslp_downloader.downloader.os.remove"
        ):
            record = downloader.download("nonexistent-id", "https://imslp.org/wiki/other.pdf")

        self.assertTrue(record.file_path.endswith("IMSLP37119-PMLP01969-Chopin_Op.10_600dpi.pdf"))
        self.assertFalse(record.file_path.endswith(".pdf.pdf"))

    def test_browser_error_marks_record_failed_and_reraises(self):
        browser_cls = _mock_browser_cls(enter_side_effect=BrowserError("launch failed"))
        with patch("imslp_downloader.downloader.IMSLPBrowser", browser_cls):
            with self.assertRaises(BrowserError):
                downloader.download(str(self.version.id), self.version.imslp_url)

        record = Download.objects.get(score_id_raw=str(self.version.id))
        self.assertEqual(record.status, DownloadStatus.FAILED)
        self.assertEqual(record.error_message, "launch failed")

    def test_download_failed_marks_record_failed_and_reraises(self):
        browser_cls = _mock_browser_cls(download_file_side_effect=DownloadFailed("timed out"))
        with patch("imslp_downloader.downloader.IMSLPBrowser", browser_cls):
            with self.assertRaises(DownloadFailed):
                downloader.download(str(self.version.id), self.version.imslp_url)

        record = Download.objects.get(score_id_raw=str(self.version.id))
        self.assertEqual(record.status, DownloadStatus.FAILED)
        self.assertEqual(record.error_message, "timed out")

    def test_file_save_failed_marks_record_failed_and_reraises(self):
        downloaded = DownloadedFile(
            tmp_path="/tmp/fake.pdf", suggested_filename="fake.pdf", source_url=self.version.imslp_url
        )
        with patch(
            "imslp_downloader.downloader.IMSLPBrowser", _mock_browser_cls(downloaded)
        ), patch.object(
            downloader.storage, "validate_pdf"
        ), patch.object(
            downloader.storage, "build_relative_path", return_value=Path("scores/x.pdf")
        ), patch.object(
            downloader.storage, "save", side_effect=FileSaveFailed("disk full")
        ):
            with self.assertRaises(FileSaveFailed):
                downloader.download(str(self.version.id), self.version.imslp_url)

        record = Download.objects.get(score_id_raw=str(self.version.id))
        self.assertEqual(record.status, DownloadStatus.FAILED)
        self.assertEqual(record.error_message, "disk full")

    def test_invalid_pdf_content_never_reaches_permanent_storage(self):
        """IMSLP sometimes serves its "Subscribe" page instead of the file
        (e.g. anonymous download quota hit). That must be rejected before
        `storage.save()` commits it to the real score path -- otherwise a
        bad file sits there looking like a legitimate, if failed, download."""
        downloaded = DownloadedFile(
            tmp_path="/tmp/fake.pdf", suggested_filename="fake.pdf", source_url=self.version.imslp_url
        )
        with patch(
            "imslp_downloader.downloader.IMSLPBrowser", _mock_browser_cls(downloaded)
        ), patch.object(
            downloader.storage, "validate_pdf", side_effect=FileSaveFailed("not a valid PDF (bad header)")
        ), patch.object(
            downloader.storage, "save"
        ) as mock_save:
            with self.assertRaises(FileSaveFailed):
                downloader.download(str(self.version.id), self.version.imslp_url)

        mock_save.assert_not_called()
        record = Download.objects.get(score_id_raw=str(self.version.id))
        self.assertEqual(record.status, DownloadStatus.FAILED)
        self.assertEqual(record.error_message, "not a valid PDF (bad header)")

    def test_unexpected_exception_is_wrapped_as_download_failed(self):
        browser_cls = _mock_browser_cls(enter_side_effect=RuntimeError("boom"))
        with patch("imslp_downloader.downloader.IMSLPBrowser", browser_cls):
            with self.assertRaises(DownloadFailed):
                downloader.download(str(self.version.id), self.version.imslp_url)

        record = Download.objects.get(score_id_raw=str(self.version.id))
        self.assertEqual(record.status, DownloadStatus.FAILED)
        self.assertEqual(record.error_message, "boom")


class DownloadViewTests(TestCase):
    url = "/api/imslp/download"

    def _post(self, body):
        return self.client.post(self.url, data=json.dumps(body), content_type="application/json")

    def test_missing_score_id_returns_400(self):
        response = self._post({"imslp_url": "https://imslp.org/wiki/file.pdf"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "score_id is required"})

    def test_invalid_json_returns_400(self):
        response = self.client.post(self.url, data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "invalid JSON"})

    def test_returns_cached_download_without_calling_download(self):
        with patch(
            "imslp_downloader.api.downloader.find_existing",
            return_value=MagicMock(file_path="storage/scores/cached.pdf"),
        ) as mock_find_existing, patch("imslp_downloader.api.downloader.download") as mock_download:
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "completed", "score_id": "1", "file_path": "storage/scores/cached.pdf"}
        )
        mock_find_existing.assert_called_once_with("1")
        mock_download.assert_not_called()

    def test_successful_new_download_returns_200(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download",
            return_value=MagicMock(file_path="storage/scores/new.pdf"),
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "completed", "score_id": "1", "file_path": "storage/scores/new.pdf"}
        )

    def test_invalid_imslp_url_returns_400(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download", side_effect=InvalidIMSLPURL("Not an IMSLP URL")
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://example.com/file.pdf"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"status": "failed", "score_id": "1", "error": "Not an IMSLP URL"}
        )

    def test_browser_error_returns_502(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download", side_effect=BrowserError("launch failed")
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "launch failed")

    def test_subscription_required_returns_503(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download",
            side_effect=SubscriptionRequired("IMSLP asked for a subscription"),
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "IMSLP asked for a subscription")

    def test_download_failed_returns_502(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download", side_effect=DownloadFailed("timed out")
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "timed out")

    def test_file_save_failed_returns_500(self):
        with patch("imslp_downloader.api.downloader.find_existing", return_value=None), patch(
            "imslp_downloader.api.downloader.download", side_effect=FileSaveFailed("disk full")
        ):
            response = self._post({"score_id": "1", "imslp_url": "https://imslp.org/wiki/file.pdf"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "disk full")

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
