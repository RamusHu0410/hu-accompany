"""Era judge -- phase 2 only.

Maps the piece's composition date onto a stylistic period, then measures the
whole performance against that period's performance-practice traits: not
"were the notes right" (phase 1 already answered that) but "was this played
the way music of this era is played".

Phase 2 only, because a style period is a property of the piece, not of any
one phrase, and the traits below only mean something across a whole
performance. Nothing upstream carries a composition date (imslp_search's
WorkResult/Choice and pdf_processor's piece_data have title/composer but no
date), so the caller supplies it as piece["composed_date"].

Status: structure only. Era detection and the per-era trait data are
implemented; the prose in each `_<era>_feedback` builder is deliberately
left unimplemented, so Era.json comes out with era/label/traits filled in
and an empty findings list.
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .. import Finding, JudgeResult, PieceContext

NAME = "era"
PHASE = 2

# Era keys -- also the values surfaced in the stored Era.json.
RENAISSANCE = "renaissance"
BAROQUE = "baroque"
CLASSICAL = "classical"
ROMANTIC = "romantic"
LATE_ROMANTIC = "late_romantic"
MODERN = "modern"
CONTEMPORARY = "contemporary"

# Style periods don't have hard edges: a year this close to a boundary is
# treated as transitional, and adjacent_era() exposes the neighbouring era so
# feedback can hedge (e.g. "late Classical / early Romantic").
TRANSITION_MARGIN_YEARS = 15


@dataclass(frozen=True)
class EraProfile:
    """A style period plus the performance-practice traits feedback for that
    period should key on. `start_year`/`end_year` are inclusive; None means
    open-ended. `emphasis` multiplies a score dimension's importance when
    weighing which traits matter most for this era."""

    era: str
    label: str
    start_year: Optional[int]
    end_year: Optional[int]
    traits: Tuple[str, ...]
    emphasis: Dict[str, float]


# Chronological, non-overlapping. Boundaries follow the conventional
# musicological dates (Baroque 1600, Classical 1750, Romantic 1820).
ERA_PROFILES: Tuple[EraProfile, ...] = (
    EraProfile(
        era=RENAISSANCE,
        label="Renaissance",
        start_year=None,
        end_year=1599,
        traits=(
            "vocal-derived, modal melodic lines that move by step",
            "even, flowing pulse without metric accent hierarchy",
            "flat dynamic plane -- shaping comes from line, not volume",
            "no sustain pedal; clarity between independent voices",
        ),
        emphasis={"pitch": 1.2, "rhythm": 1.1, "tempo": 1.0, "articulation": 0.9, "dynamics": 0.6},
    ),
    EraProfile(
        era=BAROQUE,
        label="Baroque",
        start_year=1600,
        end_year=1749,
        traits=(
            "terraced dynamics -- block levels rather than gradual swells",
            "ornaments (trills, mordents) start on the beat and belong to the line",
            "detached, articulate touch; each contrapuntal voice stays audible",
            "steady pulse, minimal rubato outside cadences and fermatas",
            "sparse sustain pedal -- sonority comes from finger legato",
        ),
        emphasis={"pitch": 1.1, "rhythm": 1.2, "tempo": 1.2, "articulation": 1.3, "dynamics": 0.7},
    ),
    EraProfile(
        era=CLASSICAL,
        label="Classical",
        start_year=1750,
        end_year=1819,
        traits=(
            "periodic phrasing with clearly shaped cadences",
            "transparent texture: singing melody over a light accompaniment",
            "graded dynamics with restrained, phrase-local rubato",
            "sharp articulation contrasts between staccato and legato",
            "strict underlying tempo -- ornament and figuration stay in time",
        ),
        emphasis={"pitch": 1.1, "rhythm": 1.2, "tempo": 1.2, "articulation": 1.2, "dynamics": 1.0},
    ),
    EraProfile(
        era=ROMANTIC,
        label="Romantic",
        start_year=1820,
        end_year=1889,
        traits=(
            "expressive rubato: tempo bends with the phrase, then repays itself",
            "wide dynamic range built from long crescendo/diminuendo arcs",
            "singing legato supported by pedal, melody voiced above the texture",
            "inner voices and bass line shaped rather than merely played",
            "large-scale phrase architecture aimed at a climax",
        ),
        emphasis={"pitch": 1.0, "rhythm": 0.9, "tempo": 0.8, "articulation": 1.0, "dynamics": 1.3},
    ),
    EraProfile(
        era=LATE_ROMANTIC,
        label="Late Romantic / Impressionist",
        start_year=1890,
        end_year=1919,
        traits=(
            "colour and blend take priority over articulate clarity",
            "layered and half-pedalling to sustain atmosphere without mud",
            "fluid, non-metric rubato; bar lines felt loosely",
            "finely graded soft dynamics -- many distinct shades below mezzo-forte",
            "sonority as texture: chords voiced for balance, not just accuracy",
        ),
        emphasis={"pitch": 1.0, "rhythm": 0.8, "tempo": 0.8, "articulation": 0.9, "dynamics": 1.4},
    ),
    EraProfile(
        era=MODERN,
        label="Modern",
        start_year=1920,
        end_year=1974,
        traits=(
            "rhythmic precision under shifting meters and irregular groupings",
            "literal adherence to notated dynamics and articulation",
            "percussive and varied touch, including deliberately dry attacks",
            "motoric drive -- little unmarked rubato",
            "dissonance played in balance rather than softened",
        ),
        emphasis={"pitch": 1.2, "rhythm": 1.4, "tempo": 1.2, "articulation": 1.1, "dynamics": 1.0},
    ),
    EraProfile(
        era=CONTEMPORARY,
        label="Contemporary",
        start_year=1975,
        end_year=None,
        traits=(
            "strict fidelity to highly detailed notation",
            "notated silences and durations are structural -- hold them exactly",
            "extremes of register and dynamics executed without distortion",
            "extended techniques and non-standard notation read literally",
            "tempo relationships between sections kept proportional",
        ),
        emphasis={"pitch": 1.2, "rhythm": 1.3, "tempo": 1.2, "articulation": 1.1, "dynamics": 1.1},
    ),
)

ERA_PROFILES_BY_ERA: Dict[str, EraProfile] = {profile.era: profile for profile in ERA_PROFILES}


# --- Composition-date parsing / era detection --------------------------------

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_DECADE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})s\b")
_CENTURY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+century\b", re.IGNORECASE)


def parse_composed_year(composed_date) -> Optional[int]:
    """Best-effort single year from a composition date, which arrives in many
    shapes from catalogue metadata: 1810, "1810", "1810-05-03", "ca. 1785",
    "1830s", "1802-1804", "18th century". Ranges and decades collapse to
    their midpoint. Returns None when nothing year-like is present.
    """
    if composed_date is None:
        return None
    if isinstance(composed_date, bool):  # bool is an int subclass -- not a year
        return None
    if isinstance(composed_date, (int, float)):
        return int(composed_date)

    text = str(composed_date).strip()
    if not text:
        return None

    decade = _DECADE_RE.search(text)
    if decade:
        return int(decade.group(1)) + 5

    years = [int(match) for match in _YEAR_RE.findall(text)]
    if years:
        return (min(years) + max(years)) // 2

    century = _CENTURY_RE.search(text)
    if century:
        # "18th century" -> 1700..1799, take the midpoint.
        return (int(century.group(1)) - 1) * 100 + 50

    return None


def era_for_year(year: Optional[int]) -> Optional[EraProfile]:
    """The profile whose inclusive year range contains `year`, or None."""
    if year is None:
        return None
    for profile in ERA_PROFILES:
        after_start = profile.start_year is None or year >= profile.start_year
        before_end = profile.end_year is None or year <= profile.end_year
        if after_start and before_end:
            return profile
    return None


def detect_era(composed_date) -> Optional[EraProfile]:
    """Style period implied by a composition date, or None if undeterminable."""
    return era_for_year(parse_composed_year(composed_date))


def adjacent_era(year: Optional[int], margin_years: int = TRANSITION_MARGIN_YEARS) -> Optional[EraProfile]:
    """The neighbouring era when `year` sits within `margin_years` of an era
    boundary (e.g. 1815 -> Romantic, 1755 -> Baroque), else None. Lets
    feedback acknowledge transitional works instead of forcing one label.
    """
    profile = era_for_year(year)
    if profile is None:
        return None
    index = ERA_PROFILES.index(profile)
    if profile.start_year is not None and index > 0 and year - profile.start_year < margin_years:
        return ERA_PROFILES[index - 1]
    if profile.end_year is not None and index < len(ERA_PROFILES) - 1 and profile.end_year - year < margin_years:
        return ERA_PROFILES[index + 1]
    return None


# --- Per-era feedback builders (not implemented yet) -------------------------
#
# Each builder receives the detected era's profile and the whole-piece
# context (piece metadata, every phase-1 phrase file, aggregated scores, and
# every phase-1 finding), and returns this era's Findings -- i.e. how the
# performance measured up against *that era's* traits, not just against the
# notes. Deliberately left blank; only the dispatch structure is in place.


def _renaissance_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _baroque_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _classical_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _romantic_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _late_romantic_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _modern_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


def _contemporary_feedback(profile: EraProfile, ctx: PieceContext) -> List[Finding]:
    pass


_ERA_FEEDBACK_BUILDERS: Dict[str, Callable[[EraProfile, PieceContext], List[Finding]]] = {
    RENAISSANCE: _renaissance_feedback,
    BAROQUE: _baroque_feedback,
    CLASSICAL: _classical_feedback,
    ROMANTIC: _romantic_feedback,
    LATE_ROMANTIC: _late_romantic_feedback,
    MODERN: _modern_feedback,
    CONTEMPORARY: _contemporary_feedback,
}


def build_era_summary(profile: EraProfile, findings: List[Finding], transitional: Optional[EraProfile]) -> str:
    """One-line era framing for the phase-2 summary. Not implemented yet."""
    pass


def judge(ctx: PieceContext) -> JudgeResult:
    """Era-aware slice of the whole-piece feedback.

    Detects the style period from piece["composed_date"] and dispatches to
    that era's builder. When the date is missing/unparseable or falls
    outside the covered ranges, `era`/`label` come back None with no
    findings, so callers can simply omit the section.
    """
    year = parse_composed_year((ctx.piece or {}).get("composed_date"))
    profile = era_for_year(year)
    if profile is None:
        return JudgeResult(
            category=NAME,
            score=None,
            details={"era": None, "label": None, "composed_year": year, "traits": [], "summary": ""},
        )

    builder = _ERA_FEEDBACK_BUILDERS.get(profile.era)
    findings = (builder(profile, ctx) if builder is not None else None) or []
    transitional = adjacent_era(year)

    return JudgeResult(
        category=NAME,
        score=None,
        findings=findings,
        details={
            "era": profile.era,
            "label": profile.label,
            "composed_year": year,
            "transitional_with": transitional.label if transitional else None,
            "traits": list(profile.traits),
            "summary": build_era_summary(profile, findings, transitional) or "",
        },
    )
