"""Tempo judge: does the pulse hold across the phrase, or does it gradually
slow down / rush?

Measured as the change in mean onset offset between the first and second
half of the phrase, so a phrase that is uniformly a little behind the click
(one steady tempo, just offset) is not reported as drifting.
"""

from typing import List, Tuple

from .. import (
    ExpectedNote,
    Finding,
    JudgeResult,
    PhraseContext,
    UserNote,
    confidence_for,
    score_falloff,
    severity_for,
)
from .rhythm import onset_thresholds

NAME = "tempo"
PHASE = 1

MIN_MATCHED_NOTES_FOR_TREND = 4


def _mean_offset(pairs: List[Tuple[ExpectedNote, UserNote]]) -> float:
    return sum(user.start_time_ms - expected.start_time_ms for expected, user in pairs) / len(pairs)


def judge(ctx: PhraseContext) -> JudgeResult:
    matched = sorted(ctx.matched, key=lambda pair: pair[0].start_time_ms)
    if len(matched) < MIN_MATCHED_NOTES_FOR_TREND:
        # Too few notes for a trend to mean anything -- no score, so tempo
        # simply drops out of the overall for this phrase.
        return JudgeResult(category=NAME, score=None, details={"insufficient_data": True})

    mid = len(matched) // 2
    drift_ms = _mean_offset(matched[mid:]) - _mean_offset(matched[:mid])
    drift_abs = abs(drift_ms)
    minor, major = onset_thresholds(ctx.beat_ms)

    score = round(score_falloff(drift_abs, minor, major * 2))
    severity = severity_for(drift_abs, minor, major)
    findings: List[Finding] = []
    if severity is not None:
        direction = "slowing" if drift_ms > 0 else "rushing"
        verb = "slows down" if drift_ms > 0 else "rushes"
        findings.append(
            Finding(
                bars=ctx.bar(matched[0][0].start_time_ms),
                category=NAME,
                severity=severity,
                confidence=confidence_for(drift_abs, minor, major),
                message=f"The tempo gradually {verb} across the phrase.",
                details={
                    "drift_ms": round(drift_ms, 1),
                    "direction": direction,
                    "through_bar": ctx.bar(matched[-1][0].start_time_ms),
                    "suggestion": "Practice the phrase with a metronome, paying close attention to keeping a steady tempo through to the end.",
                },
            )
        )

    return JudgeResult(
        category=NAME,
        score=score,
        findings=findings,
        details={"insufficient_data": False, "drift_ms": round(drift_ms, 1)},
    )
