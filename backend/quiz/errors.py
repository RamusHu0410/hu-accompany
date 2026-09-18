class QuizError(Exception):
    """Base class for errors raised by the quiz package."""


class InvalidQuizRequest(QuizError):
    """Raised when the request body is missing `topic`, or `topic` is blank
    or not a string. The caller sent something structurally wrong, so this
    maps to 400 rather than an empty quiz."""


class UnknownTopic(QuizError):
    """Raised when a topic string parses but names no era this package has a
    question bank for. Deliberately distinct from [InvalidQuizRequest]: the
    request was well formed, there is simply nothing to ask about yet, and
    the API layer answers with the list of eras that *are* covered."""
