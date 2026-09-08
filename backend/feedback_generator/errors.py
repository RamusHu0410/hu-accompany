class FeedbackGeneratorError(Exception):
    """Base class for errors raised by the feedback_generator package."""


class InvalidNoteData(FeedbackGeneratorError):
    """Raised when a note dict in the request is missing a required field
    or has a value of the wrong type/out of range (e.g. bpm <= 0)."""


class InvalidSessionId(FeedbackGeneratorError):
    """Raised when a caller-supplied session id (or phase-2 file name) isn't
    a plain identifier. Both become path segments under storage/feedback/,
    so anything containing a separator or '..' is rejected rather than
    sanitized."""


class StorageFailed(FeedbackGeneratorError):
    """Raised when a feedback file can't be read or written (bad
    permissions, disk full, corrupt JSON). Callers should treat this as
    non-fatal -- the feedback itself is still valid, it just wasn't saved."""
