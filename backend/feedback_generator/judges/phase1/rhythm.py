"""Rhythm judge: note onsets (early/late) and note lengths (held too long /
cut short) on matched notes.

Onset thresholds are tempo-relative -- 60ms is inside the beat at 60bpm and
well outside it at 200bpm -- with an absolute floor so they stay meaningful
at very slow tempi. Note-length thresholds are relative to the written
duration instead, since a 15% overhang means the same thing on a long note
as on a short one.

Drift of the pulse *across* the phrase is a separate dimension: tempo.py.
"""

from typing import List, Optional

from .. import (
    ExpectedNote,
    Finding,
    JudgeResult,
    PhraseContext,
    UserNote,
    confidence_for,
    effective_threshold_ms,
    score_falloff,
    severity_for,
)

NAME = "rhythm"
PHASE = 1

TIMING_MINOR_FRACTION_OF_BEAT = 0.10
TIMING_MAJOR_FRACTION_OF_BEAT = 0.25
TIMING_MINOR_FLOOR_MS = 15.0
TIMING_MAJOR_FLOOR_MS = 40.0

DURATION_MINOR_PCT = 0.15  # |user_dur - expected_dur| / expected_dur
DURATION_MAJOR_PCT = 0.35
DURATION_FLOOR_MS = 20.0


def onset_thresholds(beat_ms: float) -> tuple:
    return (
        effective_threshold_ms(TIMING_MINOR_FRACTION_OF_BEAT, TIMING_MINOR_FLOOR_MS, beat_ms),
        effective_threshold_ms(TIMING_MAJOR_FRACTION_OF_BEAT, TIMING_MAJOR_FLOOR_MS, beat_ms),
    )


def duration_thresholds(expected_duration_ms: float) -> tuple:
    return (
        max(DURATION_FLOOR_MS, DURATION_MINOR_PCT * expected_duration_ms),
        max(DURATION_FLOOR_MS, DURATION_MAJOR_PCT * expected_duration_ms),
    )


def _onset_finding(ctx: PhraseContext, expected: ExpectedNote, user: UserNote) -> Optional[Finding]:
    diff_ms = user.start_time_ms - expected.start_time_ms
    diff_abs = abs(diff_ms)
    minor, major = onset_thresholds(ctx.beat_ms)
    severity = severity_for(diff_abs, minor, major)
    if severity is None:
        return None

    direction = "late" if diff_ms > 0 else "early"
    return Finding(
        bars=ctx.bar(expected.start_time_ms),
        category=NAME,
        severity=severity,
        confidence=confidence_for(diff_abs, minor, major),
        message=f"This note came in {direction}, disrupting the rhythm.",
        details={
            "note_id": expected.note_id,
            "issue": "onset",
            "diff_ms": round(diff_ms, 1),
            "direction": direction,
            "suggestion": "Practice this passage with a metronome, focusing on landing the note exactly on the beat.",
        },
    )


def _duration_finding(ctx: PhraseContext, expected: ExpectedNote, user: UserNote) -> Optional[Finding]:
    if expected.duration_ms <= 0:
        return None
    diff_ms = user.duration_ms - expected.duration_ms
    diff_abs = abs(diff_ms)
    minor, major = duration_thresholds(expected.duration_ms)
    severity = severity_for(diff_abs, minor, major)
    if severity is None:
        return None

    if diff_ms > 0:
        direction, message = "too_long", "This note was held longer than written."
    else:
        direction, message = "too_short", "This note was cut short compared to what's written."

    return Finding(
        bars=ctx.bar(expected.start_time_ms),
        category=NAME,
        severity=severity,
        confidence=confidence_for(diff_abs, minor, major),
        message=message,
        details={
            "note_id": expected.note_id,
            "issue": "duration",
            "diff_ms": round(diff_ms, 1),
            "pct": round(diff_abs / expected.duration_ms, 3),
            "direction": direction,
            "suggestion": "Slow down and count out this note's full written duration before returning to full tempo.",
        },
    )


def _note_score(ctx: PhraseContext, expected: ExpectedNote, user: UserNote) -> float:
    onset_minor, onset_major = onset_thresholds(ctx.beat_ms)
    onset_score = score_falloff(
        abs(user.start_time_ms - expected.start_time_ms), onset_minor, onset_major * 2
    )

    if expected.duration_ms:
        duration_minor, duration_major = duration_thresholds(expected.duration_ms)
    else:
        duration_minor = duration_major = DURATION_FLOOR_MS
    duration_score = score_falloff(
        abs(user.duration_ms - expected.duration_ms), duration_minor, duration_major * 2
    )

    return (onset_score + duration_score) / 2


def judge(ctx: PhraseContext) -> JudgeResult:
    findings: List[Finding] = []
    for expected, user in ctx.matched:
        for finding in (_onset_finding(ctx, expected, user), _duration_finding(ctx, expected, user)):
            if finding is not None:
                findings.append(finding)

    total = len(ctx.matched) + len(ctx.missing)
    if total == 0:
        score = None
    else:  # notes that were never played contribute 0
        score = round(sum(_note_score(ctx, e, u) for e, u in ctx.matched) / total)

    return JudgeResult(category=NAME, score=score, findings=findings)
