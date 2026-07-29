class PipelineError(Exception):
    """Base class for errors raised by the music score parsing pipeline."""


class InvalidPDFError(PipelineError):
    """Raised when the input file doesn't exist, isn't a valid PDF, or has no pages."""


class RenderError(PipelineError):
    """Raised when a page fails to rasterize (corrupt page, out-of-memory, ...)."""
