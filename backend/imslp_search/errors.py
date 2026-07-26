class IMSLPError(Exception):
    """Base class for errors raised by the imslp_search package."""


class IMSLPNetworkError(IMSLPError):
    """Raised when IMSLP could not be reached or returned a bad response."""


class WorkNotFoundError(IMSLPError):
    """Raised when no matching work could be found on IMSLP."""
