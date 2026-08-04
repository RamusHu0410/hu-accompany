"""Core IMSLP download orchestration: locate the score, drive the browser
through IMSLP's normal download flow, store the result, and keep the
Download row's status in sync throughout (Phase 3/4/6 of the design doc).
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from api.models import Version

from . import storage
from .browser import IMSLPBrowser
from .exceptions import BrowserError, DownloadFailed, FileSaveFailed, InvalidIMSLPURL
from .models import Download, DownloadStatus


def _validate_url(url: str) -> None:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc.endswith("imslp.org"):
        raise InvalidIMSLPURL(f"Not an IMSLP URL: {url!r}")


def _find_score(score_id: str):
    try:
        return Version.objects.filter(id=score_id).first()
    except (ValueError, TypeError):
        return None


def find_existing(score_id: str):
    """Return a cached COMPLETED download whose file still exists on disk,
    or None if a fresh download is needed."""
    download = (
        Download.objects.filter(score_id_raw=score_id, status=DownloadStatus.COMPLETED)
        .order_by("-updated_at")
        .first()
    )
    if download and storage.exists(download.file_path):
        return download
    return None


def download(score_id: str, imslp_url: str) -> Download:
    """Download the PDF for `score_id`, preferring the metadata service's
    own record of its URL (imslp_url) over the client-supplied one, which is
    only a fallback for when that row has been evicted from the cache."""
    version = _find_score(score_id)
    url = version.imslp_url if version else imslp_url
    _validate_url(url)

    record = Download.objects.create(
        score=version,
        score_id_raw=score_id,
        imslp_url=url,
        status=DownloadStatus.PENDING,
    )
    record.status = DownloadStatus.DOWNLOADING
    record.save(update_fields=["status", "updated_at"])

    try:
        with IMSLPBrowser() as browser:
            downloaded = browser.download_file(url)

        work_title = version.work.title if version else ""
        composer = version.work.composer if version else ""
        choice_name = version.name if version else Path(downloaded.suggested_filename).stem

        relative_path = storage.build_relative_path(
            work_title, composer, choice_name, downloaded.suggested_filename
        )
        size = storage.save(downloaded.tmp_path, relative_path)
        storage.validate_pdf(relative_path)
        os.remove(downloaded.tmp_path)

        record.status = DownloadStatus.COMPLETED
        record.file_path = storage.to_db_path(relative_path)
        record.file_name = downloaded.suggested_filename
        record.file_size = size
        record.error_message = None
        record.save()
    except (BrowserError, DownloadFailed, FileSaveFailed) as exc:
        record.status = DownloadStatus.FAILED
        record.error_message = str(exc)
        record.save()
        raise
    except Exception as exc:
        record.status = DownloadStatus.FAILED
        record.error_message = str(exc)
        record.save()
        raise DownloadFailed(str(exc)) from exc

    return record
