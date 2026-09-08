"""Note-content judge: written notes that were never played, and played
notes that aren't written.

No score of its own -- a dropped note already costs the pitch and rhythm
judges (both average over matched + missing, so a missing note counts as a
zero there). Scoring it a third time here would triple-penalize it.
"""

from typing import List

from .. import Finding, JudgeResult, PhraseContext, hz_to_note_name

NAME = "notes"
PHASE = 1


def judge(ctx: PhraseContext) -> JudgeResult:
    findings: List[Finding] = []

    for expected in ctx.missing:
        findings.append(
            Finding(
                bars=ctx.bar(expected.start_time_ms),
                category=NAME,
                severity="major",
                confidence=1.0,
                message="This note was not played.",
                details={
                    "note_id": expected.note_id,
                    "issue": "missing_note",
                    "expected_hz": expected.pitch_hz,
                    "expected_note": hz_to_note_name(expected.pitch_hz),
                    "suggestion": "Go through this passage slowly, note-by-note, to make sure this note is included.",
                },
            )
        )

    for user in ctx.extra:
        findings.append(
            Finding(
                bars=ctx.bar(user.start_time_ms),
                category=NAME,
                severity="major",
                confidence=1.0,
                message="An extra note was played that isn't in the score.",
                details={
                    "note_id": user.note_id,
                    "issue": "extra_note",
                    "user_hz": user.pitch_hz,
                    "user_note": hz_to_note_name(user.pitch_hz),
                    "suggestion": "Review the written notes here closely and avoid adding notes that aren't written.",
                },
            )
        )

    findings.sort(key=lambda f: f.bars)
    return JudgeResult(category=NAME, score=None, findings=findings)
