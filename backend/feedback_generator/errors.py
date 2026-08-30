class FeedbackGeneratorError(Exception):
    """Base class for errors raised by the feedback_generator package."""


class InvalidNoteData(FeedbackGeneratorError):
    """Raised when a note dict in the request is missing a required field
    or has a value of the wrong type/out of range (e.g. bpm <= 0)."""
