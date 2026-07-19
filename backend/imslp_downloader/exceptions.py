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


class FileSaveFailed(IMSLPDownloaderError):
    """Raised when the downloaded bytes can't be persisted to storage
    (disk full, permissions, failed integrity validation, ...)."""
