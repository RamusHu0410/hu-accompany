"""Phase 2: turn every phase-1 phrase file into one whole-piece summary.

Phase 1 reports what happened bar by bar and says nothing about the piece as
a whole; this module is the only place that aggregates -- it averages the
judges' per-phrase ratings, ranks the recurring problems, picks what went
well, and writes the one-line summary. It reads only stored findings and
scores, never notes, so it stays independent of how any judge measured
what it measured.
"""

import dataclasses
from typing import Dict, List, Optional

from .judges import Finding, PieceContext, bar_span, overall_score

SCORE_DIMENSIONS = ("pitch", "rhythm", "tempo", "dynamics", "articulation")

POSITIVE_SCORE_THRESHOLD = 90
MIN_WEIGHT_TO_SURFACE = 1.0
MAX_MAIN_FEEDBACK_ITEMS = 3

# A finding's "group" is its category, or category/issue where one judge
# reports distinct problems (rhythm reports onsets and note lengths; notes
# reports dropped and added notes).
def group_key(finding: dict) -> str:
    issue = (finding.get("details") or {}).get("issue")
    category = finding.get("category", "")
    return f"{category}/{issue}" if issue else category


# How much a group's weight (frequency x severity) is scaled before ranking
# -- keeps repeated, musically-core problems (wrong notes, dropped notes)
# ahead of less critical ones (articulation nuance) even when raw counts are
# similar.
GROUP_IMPORTANCE = {
    "pitch": 1.2,
    "notes/missing_note": 1.2,
    "rhythm/onset": 1.1,
    "tempo": 1.0,
    "rhythm/duration": 0.9,
    "notes/extra_note": 0.9,
    "articulation": 0.7,
}

# Which 0-100 dimension(s) each group reflects, used to avoid praising a
# dimension that's already been flagged as a problem.
GROUP_TO_SCORE_DIMENSION = {
    "pitch": {"pitch"},
    "rhythm/onset": {"rhythm"},
    "rhythm/duration": {"rhythm"},
    "notes/missing_note": {"pitch", "rhythm"},
    "notes/extra_note": {"pitch", "rhythm"},
    "articulation": {"articulation"},
    "tempo": {"tempo"},
}

POSITIVE_TEMPLATES = {
    "pitch": "Pitch accuracy was strong.",
    "rhythm": "Rhythmic accuracy was strong.",
    "tempo": "Tempo stayed steady and consistent.",
    "dynamics": "Dynamics were well controlled.",
    "articulation": "Articulation matched the markings well.",
}


def _group_message(key: str, count: int) -> tuple:
    """(description, practice_action) for one recurring problem."""
    plural = count != 1
    templates = {
        "pitch": (
            f"Pitch was inaccurate on {count} notes across the piece." if plural else "One note's pitch was noticeably off.",
            "Isolate the affected note(s) and check them against the expected pitch before playing at full tempo.",
        ),
        "rhythm/onset": (
            f"{count} notes were noticeably early or late." if plural else "One note's timing was noticeably off.",
            "Practice the affected bars with a metronome, focusing on landing each note exactly on the beat.",
        ),
        "rhythm/duration": (
            f"{count} notes were held for noticeably longer or shorter than written." if plural else "One note's length didn't match what was written.",
            "Slow the affected bars down and count out each note's full written duration before speeding back up.",
        ),
        "notes/missing_note": (
            f"{count} expected notes were not played." if plural else "One expected note was not played.",
            "Go through the affected bars slowly note-by-note to make sure every note is played.",
        ),
        "notes/extra_note": (
            f"{count} extra notes were played that weren't in the score." if plural else "An extra note was played that wasn't in the score.",
            "Review the written notes for these bars closely and remove any notes that aren't written.",
        ),
        "articulation": (
            f"Articulation didn't match the marking on {count} notes." if plural else "One note's articulation didn't match the marking.",
            "Practice the marked articulation in isolation -- short and detached for staccato, smooth and connected for legato -- before playing at full tempo.",
        ),
        "tempo": (
            f"The tempo drifts across {count} phrases." if plural else "The tempo drifts across one phrase.",
            "Practice those phrases with a metronome, paying close attention to keeping a steady tempo through to the end.",
        ),
    }
    return templates.get(
        key,
        (f"{count} issues were flagged in this category.", "Review the affected bars slowly."),
    )


# --- Aggregation --------------------------------------------------------------

def aggregate_scores(phrases: List[dict]) -> Dict[str, Optional[int]]:
    """Mean of each dimension across the phrases that scored it, then one
    overall over the dimensions that survived. A dimension no phrase could
    rate (dynamics today) stays None instead of counting as zero."""
    scores: Dict[str, Optional[int]] = {}
    for dimension in SCORE_DIMENSIONS:
        values = [
            entry["scores"][dimension]
            for entry in phrases
            if isinstance(entry.get("scores"), dict) and entry["scores"].get(dimension) is not None
        ]
        scores[dimension] = round(sum(values) / len(values)) if values else None
    return {"overall": overall_score(scores), **scores}


def collect_findings(phrases: List[dict]) -> List[dict]:
    """Every phase-1 finding, flattened in phrase order."""
    return [finding for entry in phrases for finding in entry.get("feedback", [])]


def build_piece_context(piece: Optional[dict], phrases: List[dict]) -> PieceContext:
    """The context phase-2 judges and this summary both run on."""
    return PieceContext(
        piece=piece or {},
        phrases=phrases,
        scores=aggregate_scores(phrases),
        findings=collect_findings(phrases),
    )


# --- Main feedback / positives / summary line ---------------------------------

def _group_boxes(group: List[dict]) -> List[dict]:
    """Every distinct bar box behind one group of findings, in bar order --
    a recurring problem spans several bars, so the summary marks all of
    them rather than only the first. Empty when the phase-1 findings carry
    no boxes (a score processed before bar boxes existed, or judged without
    them -- see orchestrator.judge_phrase)."""
    by_bar = {
        f.get("bars") or 0: f["box"] for f in group if isinstance(f.get("box"), dict)
    }
    return [by_bar[bar] for bar in sorted(by_bar)]


def build_main_feedback(findings: List[dict]) -> List[Finding]:
    """The piece's top recurring problems, most important first."""
    groups: Dict[str, List[dict]] = {}
    for finding in findings:
        groups.setdefault(group_key(finding), []).append(finding)

    weighted = []
    for key, group in groups.items():
        weight = sum(2 if f.get("severity") == "major" else 1 for f in group) * GROUP_IMPORTANCE.get(key, 1.0)
        if weight < MIN_WEIGHT_TO_SURFACE:
            continue
        description, practice_action = _group_message(key, len(group))
        bars = bar_span(f.get("bars", 0) for f in group)
        confidences = [f.get("confidence", 1.0) for f in group]
        boxes = _group_boxes(group)
        weighted.append(
            (
                weight,
                Finding(
                    bars=bars[0] if bars else 0,
                    category=group[0].get("category") or key,
                    severity="major" if any(f.get("severity") == "major" for f in group) else "minor",
                    confidence=round(max(confidences), 2) if confidences else 1.0,
                    message=description,
                    details={
                        "issue": key,
                        "count": len(group),
                        "bars": bars,
                        "boxes": boxes,
                        "suggestion": practice_action,
                    },
                ),
            )
        )

    weighted.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in weighted][:MAX_MAIN_FEEDBACK_ITEMS]


def build_positive_feedback(scores: Dict[str, Optional[int]], main_feedback: List[Finding]) -> List[str]:
    """Praise only dimensions that scored well *and* weren't just flagged --
    no forced compliments."""
    flagged = set()
    for item in main_feedback:
        flagged |= GROUP_TO_SCORE_DIMENSION.get(item.details.get("issue", ""), {item.category})

    candidates = []
    for dimension, template in POSITIVE_TEMPLATES.items():
        score = scores.get(dimension)
        if score is not None and score >= POSITIVE_SCORE_THRESHOLD and dimension not in flagged:
            candidates.append((score, template))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [template for _, template in candidates[:2]]


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if text else text


def _strip_period(text: str) -> str:
    return text[:-1] if text.endswith(".") else text


def build_summary_line(main_feedback: List[Finding], positive_feedback: List[str]) -> str:
    if positive_feedback and main_feedback:
        return f"{_strip_period(positive_feedback[0])}, but {_lower_first(_strip_period(main_feedback[0].message))}."
    if positive_feedback:
        return f"{positive_feedback[0]} No significant issues were detected."
    if main_feedback:
        return main_feedback[0].message
    return "No significant issues were detected."


def summarize(ctx: PieceContext) -> dict:
    """Phase 2's Summary.json body: the whole-piece scores, the top
    problems, what went well, and one line tying them together."""
    main_feedback = build_main_feedback(ctx.findings)
    positive_feedback = build_positive_feedback(ctx.scores, main_feedback)
    return {
        "type": "summary",
        "piece": ctx.piece,
        "phrases": [entry.get("phrase") for entry in ctx.phrases],
        "scores": ctx.scores,
        "summary": build_summary_line(main_feedback, positive_feedback),
        "positive_feedback": positive_feedback,
        "feedback": [dataclasses.asdict(item) for item in main_feedback],
    }
