class IMSLPDownloaderError(Exception):
    """Base class for errors raised by the imslp_downloader package."""


class InvalidIMSLPURL(IMSLPDownloaderError):
    """Raised when the given URL isn't a downloadable IMSLP file URL."""


class BrowserError(IMSLPDownloaderError):
    """Raised when the Playwright browser/context fails to do its job
    (launch failure, page crash, disclaimer flow changed shape, ...)."""


class DownloadFailed(IMSLPDownloaderError):
    """Raised when IMSLP never delivers the file (timeout, network error,
    the file is missing/removed, ...)."""


class SubscriptionRequired(DownloadFailed):
    """Raised when IMSLP serves its "Subscribe" gate instead of the file --
    typically the free/anonymous daily download quota for imslp.org's own
    file host has been used up for this IP. Files mirrored elsewhere (e.g.
    imslp.eu) aren't subject to this and download normally. Not fixable
    client-side; the caller should retry later."""


class FileSaveFailed(IMSLPDownloaderError):
    """Raised when the downloaded bytes can't be persisted to storage
    (disk full, permissions, failed integrity validation, ...)."""
