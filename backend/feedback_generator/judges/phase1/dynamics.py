"""Dynamics judge: loudness, from native_ffi's per-note `volume`.

`volume` is 0.0-1.0 spaced in decibels (0.1 = 6 dB) and relative to the
phone and microphone, so a reading is never mapped to pp..ff directly. Every
check compares notes with other notes in the same phrase:

    contrast  a new written level (p -> f) moves the right way, by at least
              CONTRAST_PER_STEP for each step along LEVELS
    hairpin   a cresc./dim. grows or fades from its first notes to its last
    accent    an accented / sf note stands out above its neighbours
    evenness  any other note stays close to the level around it

Written dynamics come from ExpectedNote.markings. pdf_processor puts a
marking's text only on the note it is printed at, so a level carries forward
to later notes until the next one. Notes before the phrase's first marking
have no known level: they are checked for evenness, not for contrast.

Notes struck together (a chord) are judged as one event at the loudest
member's volume, since they share one moment of sound.

Score: the mean of the marking checks (contrast / hairpin / accent) blended
with the mean evenness, MARKED_WEIGHT going to the markings; an unmarked
phrase scores on evenness alone. None when no matched note carries a volume
(an older client), so dynamics drops out of the overall instead of counting
as perfect.

Known limit (rust_samples/README.md): in legato, a soft note right after a
loud one can read high from the previous note's ring-out. So a note is never
flagged as too loud when the event before it was louder still -- that
louder event is the one that gets flagged.
"""

import re
from dataclasses import dataclass, field
from statistics import mean, median
from typing import List, Optional, Tuple

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
from ..feedbacks import DYNAMICS_ACCENT, DYNAMICS_CONTRAST, DYNAMICS_HAIRPIN, DYNAMICS_UNEVEN, Feedback

NAME = "dynamics"
PHASE = 1

DB_PER_VOLUME_UNIT = 60.0  # volume 0..1 spans -60..0 dBFS

# --- Marking vocabulary (matches pdf_processor/part2_markings/vocabulary.py) --

LEVELS = ("ppp", "pp", "p", "mp", "mf", "f", "ff", "fff")
LEVEL_RANK = {word: rank for rank, word in enumerate(LEVELS)}
CRESC_WORDS = {"cresc", "crescendo"}
DIM_WORDS = {"dim", "dimin", "diminuendo", "decresc", "decrescendo"}
ACCENT_WORDS = {"sf", "sfz", "sffz", "fz", "rf", "rfz", "fp", "sfp", "accent"}
IMPLIED_LEVEL = {"fp": "p", "sfp": "p"}  # loud attack, then this level from here on

# --- Thresholds, in volume units (x60 for dB) ---------------------------------
#
# Calibration: native_ffi's 05_dynamics_solo fixture read 0.35-0.38 at MIDI
# velocity 35-40 (~pp) and 0.68-0.69 at 105-110 (~ff), i.e. roughly 0.065
# per step of LEVELS. The contrast requirement asks for about half of that.

CHORD_TOLERANCE_MS = 30.0

CONTRAST_PER_STEP = 0.03  # ~1.8 dB for each step, so p -> f (3 steps) needs ~5.4 dB
HAIRPIN_MIN_CHANGE = 0.05  # ~3 dB from a hairpin's first notes to its last
ACCENT_MIN_LIFT = 0.05  # ~3 dB above the neighbouring notes
NO_CHANGE = 0.012  # under ~0.7 dB: not audible, so "missing" rather than "weak"
CONTRAST_WINDOW = 3  # events compared on each side of a change
MIN_HAIRPIN_EVENTS = 3
MARKING_ZERO_SCORE = 1.5  # a check scores 0 once short by 1.5x what it required

EVEN_NEIGHBOURS = 3  # events on each side that set the local level
EVEN_INSIGNIFICANT = 0.05  # 3 dB
EVEN_MINOR = 0.10  # 6 dB
EVEN_MAJOR = 0.15  # 9 dB
EVEN_ZERO_SCORE = 0.25  # 15 dB
MIN_EVENTS_FOR_EVENNESS = 4

MARKED_WEIGHT = 0.6


@dataclass
class _Event:
    """One onset: a single note, or every note of a chord struck together."""

    index: int
    start_ms: float
    volume: float  # the loudest member's
    notes: List[Tuple[ExpectedNote, UserNote]] = field(default_factory=list)
    level_word: Optional[str] = None  # written level in force, None = not known
    hairpin: Optional[str] = None  # "louder" / "softer" while a cresc. / dim. runs
    segment: int = 0  # bumps whenever a level or hairpin marking appears
    accented: bool = False


@dataclass
class _Segment:
    """A run of events under one written level or one hairpin."""

    events: List[_Event]
    level_word: Optional[str]
    hairpin: Optional[str]

    @property
    def steady(self) -> List[_Event]:
        """Its unaccented events -- an accent isn't the level around it."""
        return [event for event in self.events if not event.accented]


def _tokens(markings: Optional[str]) -> List[str]:
    return re.findall(r"[a-z]+", markings.lower()) if markings else []


def _db(volume_delta: float) -> float:
    return round(volume_delta * DB_PER_VOLUME_UNIT, 1)


# --- Building events and segments ---------------------------------------------


def _events(ctx: PhraseContext) -> List[_Event]:
    pairs = sorted(
        ((e, u) for e, u in ctx.matched if u.volume is not None),
        key=lambda pair: pair[0].start_time_ms,
    )
    events: List[_Event] = []
    for expected, user in pairs:
        if events and expected.start_time_ms - events[-1].start_ms <= CHORD_TOLERANCE_MS:
            events[-1].notes.append((expected, user))
            events[-1].volume = max(events[-1].volume, user.volume)
        else:
            events.append(
                _Event(index=len(events), start_ms=expected.start_time_ms, volume=user.volume, notes=[(expected, user)])
            )
    return events


def _annotate(ctx: PhraseContext, events: List[_Event]) -> None:
    """Give each event the written level / hairpin in force at it. Markings
    on missing notes still count -- a dropped note doesn't cancel its f."""
    marked = sorted(
        (note for note in [e for e, _ in ctx.matched] + list(ctx.missing) if note.markings),
        key=lambda note: note.start_time_ms,
    )
    level_word, hairpin, segment, cursor = None, None, 0, 0
    for event in events:
        horizon = event.start_ms + CHORD_TOLERANCE_MS
        while cursor < len(marked) and marked[cursor].start_time_ms <= horizon:
            for token in _tokens(marked[cursor].markings):
                implied = IMPLIED_LEVEL.get(token, token)
                if implied in LEVEL_RANK:
                    level_word, hairpin = implied, None
                    segment += 1
                elif token in CRESC_WORDS:
                    hairpin = "louder"
                    segment += 1
                elif token in DIM_WORDS:
                    hairpin = "softer"
                    segment += 1
            cursor += 1
        event.level_word, event.hairpin, event.segment = level_word, hairpin, segment
        event.accented = any(
            expected.has_accent or bool(ACCENT_WORDS.intersection(_tokens(expected.markings)))
            for expected, _ in event.notes
        )


def _segments(events: List[_Event]) -> List[_Segment]:
    segments: List[_Segment] = []
    for event in events:
        if segments and segments[-1].events[-1].segment == event.segment:
            segments[-1].events.append(event)
        else:
            segments.append(_Segment(events=[event], level_word=event.level_word, hairpin=event.hairpin))
    return segments


# --- Shared verdict / finding helpers -----------------------------------------


def _marking_verdict(change: float, required: float) -> Optional[Tuple[str, str, float]]:
    """(outcome, severity, confidence) when `change` falls short of
    `required`, else None. Both are in the direction the marking asks for."""
    if change >= required:
        return None
    weak = change > NO_CHANGE
    confidence = confidence_for(required - change, 0.0, required)
    return ("weak", "minor", confidence) if weak else ("missing", "major", confidence)


def _marking_score(change: float, required: float) -> float:
    return score_falloff(max(0.0, required - change), 0.0, MARKING_ZERO_SCORE * required)


def _finding(
    ctx: PhraseContext, event: _Event, feedback: Feedback, severity: str, confidence: float, details: dict, **values
) -> Finding:
    message, suggestion = feedback.render(**values)
    expected = event.notes[0][0]
    return Finding(
        bars=ctx.bar(expected.start_time_ms),
        category=NAME,
        severity=severity,
        confidence=confidence,
        message=message,
        details={"note_id": expected.note_id, **details, "suggestion": suggestion},
    )


# --- The four checks ----------------------------------------------------------


def _contrast(ctx: PhraseContext, segments: List[_Segment], findings: List[Finding], scores: List[float]) -> None:
    previous: Optional[_Segment] = None  # last steady stretch with a known level
    for segment in segments:
        if segment.hairpin is not None or segment.level_word is None:
            continue
        before_segment, previous = previous, segment
        if before_segment is None or before_segment.level_word == segment.level_word:
            continue
        before = [e.volume for e in before_segment.steady][-CONTRAST_WINDOW:]
        after_events = segment.steady[:CONTRAST_WINDOW]
        if not before or not after_events:
            continue

        steps = LEVEL_RANK[segment.level_word] - LEVEL_RANK[before_segment.level_word]
        direction = "louder" if steps > 0 else "softer"
        actual = median(e.volume for e in after_events) - median(before)
        change = actual if steps > 0 else -actual
        required = abs(steps) * CONTRAST_PER_STEP
        scores.append(_marking_score(change, required))

        verdict = _marking_verdict(change, required)
        if verdict is None:
            continue
        outcome, severity, confidence = verdict
        findings.append(
            _finding(
                ctx, after_events[0], DYNAMICS_CONTRAST[(direction, outcome)], severity, confidence,
                {
                    "issue": "contrast",
                    "direction": direction,
                    "marking": segment.level_word,
                    "previous": before_segment.level_word,
                    "change_db": _db(actual),
                    "required_db": _db(required),
                },
                marking=segment.level_word,
                previous=before_segment.level_word,
            )
        )


def _hairpins(ctx: PhraseContext, segments: List[_Segment], findings: List[Finding], scores: List[float]) -> None:
    for position, segment in enumerate(segments):
        if segment.hairpin is None:
            continue
        span = list(segment.steady)
        following = segments[position + 1] if position + 1 < len(segments) else None
        if len(span) < MIN_HAIRPIN_EVENTS and following is not None and following.hairpin is None:
            span += following.steady[:CONTRAST_WINDOW]  # a short hairpin is judged by where it arrives
        if len(span) < MIN_HAIRPIN_EVENTS:
            continue

        k = max(1, min(CONTRAST_WINDOW, len(span) // 2))
        actual = median(e.volume for e in span[-k:]) - median(e.volume for e in span[:k])
        change = actual if segment.hairpin == "louder" else -actual
        scores.append(_marking_score(change, HAIRPIN_MIN_CHANGE))

        verdict = _marking_verdict(change, HAIRPIN_MIN_CHANGE)
        if verdict is None:
            continue
        outcome, severity, confidence = verdict
        findings.append(
            _finding(
                ctx, span[0], DYNAMICS_HAIRPIN[(segment.hairpin, outcome)], severity, confidence,
                {
                    "issue": "hairpin",
                    "direction": segment.hairpin,
                    "through_bar": ctx.bar(span[-1].start_ms),
                    "change_db": _db(actual),
                    "required_db": _db(HAIRPIN_MIN_CHANGE),
                },
            )
        )


def _accents(ctx: PhraseContext, segments: List[_Segment], findings: List[Finding], scores: List[float]) -> None:
    for segment in segments:
        for position, event in enumerate(segment.events):
            if not event.accented:
                continue
            nearby = segment.events[max(0, position - EVEN_NEIGHBOURS): position + EVEN_NEIGHBOURS + 1]
            neighbours = [other.volume for other in nearby if not other.accented]
            if not neighbours:
                continue
            lift = event.volume - median(neighbours)
            scores.append(_marking_score(lift, ACCENT_MIN_LIFT))

            verdict = _marking_verdict(lift, ACCENT_MIN_LIFT)
            if verdict is None:
                continue
            outcome, severity, confidence = verdict
            findings.append(
                _finding(
                    ctx, event, DYNAMICS_ACCENT[("louder", outcome)], severity, confidence,
                    {"issue": "accent", "direction": "louder", "change_db": _db(lift), "required_db": _db(ACCENT_MIN_LIFT)},
                )
            )


def _evenness(
    ctx: PhraseContext, events: List[_Event], segments: List[_Segment], findings: List[Finding], scores: List[float]
) -> None:
    for segment in segments:
        steady = segment.steady
        if len(steady) < MIN_EVENTS_FOR_EVENNESS:
            continue
        for position, event in enumerate(steady):
            neighbours = steady[max(0, position - EVEN_NEIGHBOURS): position] + steady[position + 1: position + 1 + EVEN_NEIGHBOURS]
            deviation = event.volume - median(other.volume for other in neighbours)
            severity = severity_for(abs(deviation), EVEN_MINOR, EVEN_MAJOR)
            ring_out = deviation > 0 and event.index > 0 and events[event.index - 1].volume > event.volume
            if severity is not None and ring_out:
                continue  # may be the louder note before it still sounding -- neither flag nor score it

            scores.append(score_falloff(abs(deviation), EVEN_INSIGNIFICANT, EVEN_ZERO_SCORE))
            if severity is None:
                continue
            direction = "louder" if deviation > 0 else "softer"
            findings.append(
                _finding(
                    ctx, event, DYNAMICS_UNEVEN[direction], severity,
                    confidence_for(abs(deviation), EVEN_MINOR, EVEN_MAJOR),
                    {"issue": "evenness", "direction": direction, "change_db": _db(deviation)},
                )
            )


# --- Judge --------------------------------------------------------------------


def judge(ctx: PhraseContext) -> JudgeResult:
    events = _events(ctx)
    if not events:
        return JudgeResult(category=NAME, score=None, details={"unavailable": "no volume on the user notes"})

    _annotate(ctx, events)
    segments = _segments(events)

    findings: List[Finding] = []
    marking_scores: List[float] = []
    evenness_scores: List[float] = []
    _contrast(ctx, segments, findings, marking_scores)
    _hairpins(ctx, segments, findings, marking_scores)
    _accents(ctx, segments, findings, marking_scores)
    _evenness(ctx, events, segments, findings, evenness_scores)

    if marking_scores and evenness_scores:
        score = round(MARKED_WEIGHT * mean(marking_scores) + (1 - MARKED_WEIGHT) * mean(evenness_scores))
    elif marking_scores or evenness_scores:
        score = round(mean(marking_scores or evenness_scores))
    else:
        score = None  # too few notes for evenness, and no marking to check

    volumes = [user.volume for event in events for _, user in event.notes]
    findings.sort(key=lambda finding: finding.bars)
    return JudgeResult(
        category=NAME,
        score=score,
        findings=findings,
        details={
            "insufficient_data": score is None,
            "notes_with_volume": len(volumes),
            "median_dbfs": _db(median(volumes) - 1.0),
            "range_db": _db(max(volumes) - min(volumes)),
            "markings_checked": len(marking_scores),
        },
    )
