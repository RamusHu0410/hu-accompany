"""Pitch judge: intonation and wrong notes on matched notes.

Notes that were never played (or played but not written) are note-content
problems rather than intonation ones -- see notes.py.
"""

from typing import List, Optional

from .. import (
    ExpectedNote,
    Finding,
    JudgeResult,
    PhraseContext,
    UserNote,
    confidence_for,
    hz_to_cents,
    hz_to_note_name,
    score_falloff,
    severity_for,
)

NAME = "pitch"
PHASE = 1

# Anything within this many cents (1/100th of a semitone) is normal
# intonation variance, not an error. Wider than the retired
# archive/scripts/rating.py prototype's flat CENTS_TOLERANCE=10.0, since
# that compared exact synthetic fixtures rather than live human playing.
CENTS_INSIGNIFICANT = 25.0
CENTS_MINOR = 50.0  # at/above this, effectively a different note ("wrong pitch")
CENTS_ZERO_SCORE = 200.0


def _finding(ctx: PhraseContext, expected: ExpectedNote, user: UserNote) -> Optional[Finding]:
    cents = hz_to_cents(user.pitch_hz, expected.pitch_hz)
    cents_abs = abs(cents)
    severity = severity_for(cents_abs, CENTS_INSIGNIFICANT, CENTS_MINOR)
    if severity is None:
        return None

    user_name = hz_to_note_name(user.pitch_hz)
    expected_name = hz_to_note_name(expected.pitch_hz)
    if user_name == expected_name:
        message = f"This note was played slightly {'sharp' if cents > 0 else 'flat'}."
    else:
        message = f"Wrong note — you played {user_name} instead of {expected_name}."

    return Finding(
        bars=ctx.bar(expected.start_time_ms),
        category=NAME,
        severity=severity,
        confidence=confidence_for(cents_abs, CENTS_INSIGNIFICANT, CENTS_MINOR),
        message=message,
        details={
            "note_id": expected.note_id,
            "cents": round(cents, 1),
            "expected_hz": expected.pitch_hz,
            "user_hz": user.pitch_hz,
            "expected_note": expected_name,
            "user_note": user_name,
            "suggestion": "Practice this transition slowly and focus on the correct note.",
        },
    )


def _note_score(expected: ExpectedNote, user: UserNote) -> float:
    cents_abs = abs(hz_to_cents(user.pitch_hz, expected.pitch_hz))
    return score_falloff(cents_abs, CENTS_INSIGNIFICANT, CENTS_ZERO_SCORE)


def judge(ctx: PhraseContext) -> JudgeResult:
    findings: List[Finding] = []
    for expected, user in ctx.matched:
        finding = _finding(ctx, expected, user)
        if finding is not None:
            findings.append(finding)

    total = len(ctx.matched) + len(ctx.missing)
    if total == 0:
        score = None
    else:  # notes that were never played contribute 0
        score = round(sum(_note_score(e, u) for e, u in ctx.matched) / total)

    return JudgeResult(category=NAME, score=score, findings=findings)
