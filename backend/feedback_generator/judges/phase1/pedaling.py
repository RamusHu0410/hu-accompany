"""Pedaling judge -- not implemented yet.

Graphical pedal-marking detection doesn't exist anywhere in the pipeline yet
(see pdf_processor/README.md's "Known limitations"), and no user note
carries a pedal event, so there is nothing to compare. Returns no findings
and a None score, and must not produce any pedal-related rating or feedback
until both sides of the comparison exist.
"""

from .. import JudgeResult, PhraseContext

NAME = "pedaling"
PHASE = 1


def judge(ctx: PhraseContext) -> JudgeResult:
    return JudgeResult(category=NAME, score=None, details={"unavailable": "no pedal data on either side"})
