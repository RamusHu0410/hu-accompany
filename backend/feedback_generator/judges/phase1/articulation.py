"""Articulation judge: was a marked staccato actually detached, a marked
legato/marcato actually held?

Judged as played_duration / written_duration, and only on notes that carry
one of ARTICULATION_WORDS in their `markings` -- a phrase with no
articulation markings scores None rather than 100.
"""

from typing import List, Optional

from .. import (
    ExpectedNote,
    Finding,
    JudgeResult,
    PhraseContext,
    UserNote,
    score_falloff,
)

NAME = "articulation"
PHASE = 1

STACCATO_MAX_RATIO = 0.6  # played_duration / expected_duration
LEGATO_MIN_RATIO = 0.85
ARTICULATION_WORDS = {"staccato", "legato", "marcato"}


def marking_of(expected: ExpectedNote) -> Optional[str]:
    if not expected.markings:
        return None
    lowered = expected.markings.lower()
    for word in ARTICULATION_WORDS:
        if word in lowered:
            return word
    return None


def _severity_and_confidence(marking: str, ratio: float):
    """None when the note honoured its marking, else (severity, confidence)."""
    if marking == "staccato":
        if ratio <= STACCATO_MAX_RATIO:
            return None
        overshoot = (ratio - STACCATO_MAX_RATIO) / STACCATO_MAX_RATIO
        severity = "major" if ratio > STACCATO_MAX_RATIO * 1.5 else "minor"
    else:  # legato / marcato: played too short
        if ratio >= LEGATO_MIN_RATIO:
            return None
        overshoot = (LEGATO_MIN_RATIO - ratio) / LEGATO_MIN_RATIO
        severity = "major" if ratio < LEGATO_MIN_RATIO * 0.7 else "minor"
    return severity, round(min(1.0, 0.5 + overshoot), 2)


def _note_score(marking: str, ratio: float) -> float:
    if marking == "staccato":
        return 100.0 if ratio <= STACCATO_MAX_RATIO else score_falloff(ratio, STACCATO_MAX_RATIO, 1.0)
    # legato / marcato: shorter than written is the problem
    if ratio >= LEGATO_MIN_RATIO:
        return 100.0
    return score_falloff(LEGATO_MIN_RATIO - ratio, 0.0, LEGATO_MIN_RATIO)


def _finding(ctx: PhraseContext, expected: ExpectedNote, user: UserNote, marking: str, ratio: float) -> Optional[Finding]:
    verdict = _severity_and_confidence(marking, ratio)
    if verdict is None:
        return None
    severity, confidence = verdict

    if marking == "staccato":
        message = "This note was held too long for the marked staccato articulation."
    else:
        message = f"This note was cut short for the marked {marking} articulation."

    return Finding(
        bars=ctx.bar(expected.start_time_ms),
        category=NAME,
        severity=severity,
        confidence=confidence,
        message=message,
        details={
            "note_id": expected.note_id,
            "marking": marking,
            "ratio": round(ratio, 3),
            "suggestion": f"Practice this note in isolation with the marked {marking} articulation before returning to full tempo.",
        },
    )


def judge(ctx: PhraseContext) -> JudgeResult:
    findings: List[Finding] = []
    note_scores: List[float] = []

    for expected, user in ctx.matched:
        marking = marking_of(expected)
        if marking is None or expected.duration_ms <= 0:
            continue
        ratio = user.duration_ms / expected.duration_ms
        note_scores.append(_note_score(marking, ratio))
        finding = _finding(ctx, expected, user, marking, ratio)
        if finding is not None:
            findings.append(finding)

    score = round(sum(note_scores) / len(note_scores)) if note_scores else None
    return JudgeResult(category=NAME, score=score, findings=findings)
