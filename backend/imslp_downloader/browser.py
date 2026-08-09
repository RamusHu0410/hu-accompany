"""Playwright browser/context management for the IMSLP download flow.

IMSLP gates anonymous file access behind client-side steps that only run in
a real browser (confirmed by hand against the live site), and which vary
depending on which backing host a given file is served from:

1. A one-time-per-session "Disclaimer" page with an "I understand" link
   (`Special:IMSLPDisclaimerAccept/{id}`).
2. Either of, depending on host:
   - An `IMSLPImageHandler` nag page with a real (non-subscriber) countdown
     -- "Your download will continue in 15 seconds..." -- that, once it hits
     zero, reveals an `<a>` link reading "Click here to continue your
     download." pointing straight at the file.
   - On the IMSLP-EU mirror (imslp.eu/linkhandler.php), a second, differently
     worded disclaimer page with an "I understand, continue" button instead.
   Some files skip this step entirely and start downloading right after the
   first disclaimer.

A plain HTTP client can't get through any of these (all JS-driven), so we
drive a headless Chromium instance through them instead. Once past them,
IMSLP typically serves the PDF inline (no `Content-Disposition: attachment`)
rather than triggering a real browser download, so whatever page we land on
after these steps is fetched directly instead of waiting on a `download`
event that may never come.
"""

import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import sync_playwright

from .exceptions import BrowserError, DownloadFailed, SubscriptionRequired

# IMSLP runs every request through a JS-driven anti-bot redirect chain
# (friendlyredirect.html -> friendlyredirect2.html -> the real page) before
# landing on the requested URL, observed to take ~18s on its own -- so this
# needs real headroom above that, not just above normal page-load time.
NAV_TIMEOUT_MS = 45000
# IMSLP (and its EU mirror in particular) throttles anonymous/non-donor
# downloads hard -- observed ~65KB/s for a 14MB file (~220s), confirmed with
# a plain curl too so it isn't a Playwright artifact. Larger scores are
# common on IMSLP (50MB+ full scores), so this needs real headroom.
DEFAULT_DOWNLOAD_TIMEOUT_S = 600
CLICK_TIMEOUT_MS = 8000
NATIVE_DOWNLOAD_GRACE_S = 5
POLL_INTERVAL_S = 1

# Tried in order, best-effort, after the initial page load -- each is a
# no-op if its link/button isn't present on whatever page/host this
# particular file's flow actually uses.
CONFIRM_CLICK_TEXTS = (
    "I understand",  # imslp.org's own one-time disclaimer
    "Click here to continue your download.",  # imslp.org's countdown nag page
    "I understand, continue",  # imslp.eu (IMSLP-EU mirror)'s disclaimer
)


def _guess_filename(url: str, headers: dict) -> str:
    """Best-effort filename for a fetched file: Content-Disposition first,
    then IMSLP's linkhandler.php `path` query param (which carries the real
    filename even though the endpoint's own path doesn't), then whatever's
    left of the URL path."""
    content_disposition = headers.get("content-disposition", "")
    match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';]+)', content_disposition)
    if match:
        return unquote(match.group(1))

    query_path = parse_qs(urlparse(url).query).get("path", [None])[0]
    if query_path:
        name = Path(unquote(query_path)).name
        if name:
            return name

    return Path(urlparse(url).path).name or "score.pdf"

# Where debug artifacts (screenshot + HTML) get dumped when IMSLP never
# delivers a file, so a failure can be diagnosed after the fact instead of
# just showing "no download happened" -- e.g. a rate-limit/CAPTCHA page
# looks identical to a slow page from the download-count check alone.
DEBUG_DIR = Path(tempfile.gettempdir()) / "imslp_downloader_failures"


def _dump_failure_artifacts(page) -> str:
    """Best-effort screenshot + HTML snapshot of the current page. Never
    raises -- a failure here should never mask the real DownloadFailed."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    base = DEBUG_DIR / f"fail_{stamp}"

    try:
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
    except Exception:
        pass

    try:
        base.with_suffix(".html").write_text(page.content())
    except Exception:
        pass

    return str(base)


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
                # "load" waits for every subresource (ads, trackers, etc.)
                # IMSLP pages often carry, which can hang well past
                # NAV_TIMEOUT_MS even though the DOM itself is ready almost
                # immediately. "domcontentloaded" is enough to interact with
                # the disclaimer/continue links below.
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except Exception as exc:
                raise DownloadFailed(f"Could not reach {url}: {exc}") from exc

            for link_text in CONFIRM_CLICK_TEXTS:
                try:
                    page.click(f"text={link_text}", timeout=CLICK_TIMEOUT_MS)
                    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
                except Exception:
                    pass  # this step's page/button isn't part of this file's flow

            if "subscribe" in (page.title() or "").lower():
                # imslp.org's own file host caps free/anonymous downloads per
                # IP per day; once that's used up it serves this page for
                # every file instead of the real one, regardless of which
                # disclaimer/confirm steps were just clicked through. Mirrors
                # (e.g. imslp.eu) aren't affected, so this is per-host, not a
                # blanket IMSLP-wide block.
                raise SubscriptionRequired(
                    "IMSLP asked for a subscription instead of serving the file "
                    "(likely the free daily download limit for this host was reached) "
                    f"-- current page: {page.url}"
                )

            # By now we should be sitting on the actual file. Give a real
            # browser download a moment in case IMSLP served this file type
            # as an attachment (some non-PDF assets), then fall back to
            # fetching whatever page we landed on directly -- covers the
            # common case where IMSLP serves the PDF inline (no
            # Content-Disposition: attachment) and Chromium's built-in PDF
            # viewer would otherwise render it instead of ever firing
            # Playwright's `download` event.
            deadline = time.monotonic() + NATIVE_DOWNLOAD_GRACE_S
            while not downloads and time.monotonic() < deadline:
                time.sleep(POLL_INTERVAL_S)

            if downloads:
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
                    tmp_path=tmp_copy,
                    suggested_filename=download.suggested_filename,
                    source_url=url,
                )

            file_url = page.url
            try:
                response = context.request.get(file_url, timeout=self.download_timeout_s * 1000)
            except Exception as exc:
                raise DownloadFailed(f"Could not fetch {file_url}: {exc}") from exc

            if not response.ok:
                raise DownloadFailed(f"Fetching {file_url} failed: HTTP {response.status}")

            suggested_filename = _guess_filename(file_url, response.headers)
            fd, tmp_copy = tempfile.mkstemp(
                prefix="imslp_", suffix=Path(suggested_filename).suffix or ".pdf"
            )
            with os.fdopen(fd, "wb") as fh:
                fh.write(response.body())

            return DownloadedFile(
                tmp_path=tmp_copy, suggested_filename=suggested_filename, source_url=file_url
            )
        finally:
            context.close()