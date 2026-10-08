"""The error every step of the audio pipeline raises when it can't go on: intake (hum → melody) and
arrangement (melody → song) share this one class, so run_pipeline can catch either side's.
"""


class PipelineError(Exception):
    """A step that can't go on.

    step     which one, e.g. "intake.normalize" or "arrange.render" (match with startswith)
    message  why, in words fit to show the user
    code     the problem for code to check, e.g. "no_tune" or "silent"; never match on message
    """

    def __init__(self, step: str, message: str, *, code: str | None = None):
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message
        self.code = code
