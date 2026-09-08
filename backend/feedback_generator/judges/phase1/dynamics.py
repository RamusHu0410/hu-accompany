"""Dynamics judge -- no data to judge on yet.

No note schema anywhere upstream (the mobile app, native_ffi, pdf_processor's
piece_data) currently carries a loudness/velocity value, so a real dynamics
rating cannot be computed without fabricating one. Returns no findings and a
None score, which drops dynamics out of the overall rather than scoring it
as perfect. Kept as a judge so it only has to be filled in here once
loudness reaches the request.
"""

from .. import JudgeResult, PhraseContext

NAME = "dynamics"
PHASE = 1


def judge(ctx: PhraseContext) -> JudgeResult:
    return JudgeResult(category=NAME, score=None, details={"unavailable": "no loudness data in note schema"})
