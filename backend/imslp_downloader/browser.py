"""Playwright browser/context management for the IMSLP download flow.

IMSLP gates anonymous file access behind two client-side steps that only run
in a real browser (confirmed by hand against the live site):

1. A one-time-per-session "Disclaimer" page with an "I understand" link
   (`Special:IMSLPDisclaimerAccept/{id}`).
2. An `IMSLPImageHandler` nag page with a real (non-subscriber) countdown --
   "Your download will continue in 15 seconds..." -- that, once it hits
   zero, reveals an `<a>` link reading "Click here to continue your
   download." pointing straight at the file. Nothing navigates there on its
   own; it has to be clicked. Some files skip this page entirely and start
   downloading right after the disclaimer.

A plain HTTP client can't get through either step (both are JS-driven), so
we drive a headless Chromium instance instead.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from .exceptions import BrowserError, DownloadFailed

NAV_TIMEOUT_MS = 20000
DEFAULT_DOWNLOAD_TIMEOUT_S = 180
DISCLAIMER_ACCEPT_TIMEOUT_MS = 5000
CONTINUE_DOWNLOAD_TIMEOUT_MS = 30000
POLL_INTERVAL_S = 1

DISCLAIMER_ACCEPT_TEXT = "I understand"
CONTINUE_DOWNLOAD_TEXT = "Click here to continue your download."


class DownloadedFile:
    def __init__(self, tmp_path: str, suggested_filename: str, source_url: str):
        self.tmp_path = tmp_path
        self.suggested_filename = suggested_filename
        self.source_url = source_url


class IMSLPBrowser:
    """Context-manager wrapper around a single headless Chromium instance."""

    def __init__(self, download_timeout_s: int = DEFAULT_DOWNLOAD_TIMEOUT_S):
        self.download_timeout_s = download_timeout_s
        self._playwright = None
        self._browser = None

    def __enter__(self):
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            self._teardown()
            raise BrowserError(f"Failed to launch browser: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        self._teardown()

    def _teardown(self):
        try:
            if self._browser:
                self._browser.close()
        finally:
            self._browser = None
            if self._playwright:
                self._playwright.stop()
            self._playwright = None

    def download_file(self, url: str) -> DownloadedFile:
        """Navigate to an IMSLP file URL and drive it through to a real
        download, returning a copy of the file in our own temp location
        (the browser context is closed before returning, which can reclaim
        Playwright's own download temp dir)."""
        if self._browser is None:
            raise BrowserError("IMSLPBrowser used outside its `with` block")

        try:
            context = self._browser.new_context(accept_downloads=True)
        except Exception as exc:
            raise BrowserError(f"Failed to open browser context: {exc}") from exc

        downloads = []
        context.on("download", lambda d: downloads.append(d))
        page = context.new_page()

        try:
            try:
                page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
            except Exception as exc:
                raise DownloadFailed(f"Could not reach {url}: {exc}") from exc

            try:
                page.click(f"text={DISCLAIMER_ACCEPT_TEXT}", timeout=DISCLAIMER_ACCEPT_TIMEOUT_MS)
                page.wait_for_load_state("load")
            except Exception:
                pass  # no disclaimer this time -- already accepted, or this file skips it

            try:
                page.click(
                    f"a:has-text('{CONTINUE_DOWNLOAD_TEXT}')",
                    timeout=CONTINUE_DOWNLOAD_TIMEOUT_MS,
                )
            except Exception:
                pass  # no nag page this time -- download already started, or this file skips it

            deadline = time.monotonic() + self.download_timeout_s
            while not downloads and time.monotonic() < deadline:
                time.sleep(POLL_INTERVAL_S)

            if not downloads:
                raise DownloadFailed(
                    f"IMSLP did not deliver a file within {self.download_timeout_s}s "
                    f"(current page: {page.url})"
                )

            download = downloads[0]
            failure = download.failure()
            if failure:
                raise DownloadFailed(f"Download failed: {failure}")

            src_path = download.path()
            if not src_path:
                raise DownloadFailed("Download event fired but produced no file")

            fd, tmp_copy = tempfile.mkstemp(
                prefix="imslp_", suffix=Path(download.suggested_filename).suffix or ".pdf"
            )
            os.close(fd)
            shutil.copy(src_path, tmp_copy)

            return DownloadedFile(
                tmp_path=tmp_copy, suggested_filename=download.suggested_filename, source_url=url
            )
        finally:
            context.close()
