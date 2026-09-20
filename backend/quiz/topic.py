"""Turns the free-text topic a student types into a bank lookup.

The expected shape is what an RCM cheat-sheet heading actually looks like,
e.g.

    RCM HISTORY 10 + ARCT CHEAT SHEET
    The Middle Ages (ad 476 - ad 1450)

Both lines are optional and order does not matter: the era is found by
matching known era names and their aliases anywhere in the text, and the
level is found by looking for "ARCT". Parsing is deliberately forgiving
because this is typed by hand -- a bare "baroque" resolves the same way the
full two-line heading does.
"""

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .errors import InvalidQuizRequest

# era_key -> (display name, span shown on the results screen, aliases)
ERA_ALIASES: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {
    "middle_ages": (
        "The Middle Ages",
        "ad 476 - ad 1450",
        ("middle ages", "medieval", "mediaeval", "middle age"),
    ),
    "renaissance": (
        "The Renaissance",
        "1450 - 1600",
        ("renaissance",),
    ),
    "baroque": (
        "The Baroque Era",
        "1600 - 1750",
        ("baroque",),
    ),
    "classical": (
        "The Classical Era",
        "1750 - 1825",
        ("classical era", "classical period", "classical"),
    ),
    "romantic": (
        "The Romantic Era",
        "1825 - 1900",
        ("romantic",),
    ),
    "modern": (
        "The Twentieth Century and Beyond",
        "1900 - present",
        (
            "twentieth century",
            "20th century",
            "modern",
            "contemporary",
            "impressionis",
        ),
    ),
}


@dataclass(frozen=True)
class Topic:
    era_key: str
    era_name: str
    era_span: str
    level_label: str
    include_arct: bool


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def parse_topic(raw: Optional[str]) -> Topic:
    """Parse a typed topic heading into a [Topic].

    Raises [InvalidQuizRequest] if `raw` is missing or blank. A string that
    parses but names no known era comes back with `era_key` empty, which
    generate_quiz turns into UnknownTopic -- keeping "you sent nothing" and
    "I don't cover that yet" as two different answers.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidQuizRequest("topic is required")

    text = _clean(raw).lower()

    # ARCT implies the student is past History 10, so the advanced slice of
    # each bank is unlocked. Plain "History 10" stays on the core slice.
    include_arct = "arct" in text

    era_key = ""
    # Longest alias first so "classical era" is not shadowed by "classical".
    matches = [
        (alias, key)
        for key, (_, _, aliases) in ERA_ALIASES.items()
        for alias in aliases
        if alias in text
    ]
    if matches:
        matches.sort(key=lambda pair: len(pair[0]), reverse=True)
        era_key = matches[0][1]

    era_name, era_span = ("", "")
    if era_key:
        era_name, era_span, _ = ERA_ALIASES[era_key]

    return Topic(
        era_key=era_key,
        era_name=era_name,
        era_span=era_span,
        level_label=_level_label(text, include_arct),
        include_arct=include_arct,
    )


def _level_label(text: str, include_arct: bool) -> str:
    """The level echoed back to the app, recovered from the heading so the
    results screen can title itself the way the student typed it."""
    grade = re.search(r"history\s*(\d{1,2})", text)
    if grade and include_arct:
        return f"RCM History {grade.group(1)} + ARCT"
    if grade:
        return f"RCM History {grade.group(1)}"
    if include_arct:
        return "ARCT"
    return "RCM History"


def known_eras() -> Dict[str, str]:
    """era_key -> display name, for the 'I don't cover that' response."""
    return {key: value[0] for key, value in ERA_ALIASES.items()}
