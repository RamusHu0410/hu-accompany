"""Phase 6 - Ambiguity Resolution Engine.

Spec: generate competing hypotheses for ambiguous objects (triplet vs
fingering, slur vs phrase mark, pedal "*" vs footnote, etc.) and choose the
highest-confidence interpretation only after weighing all evidence.

The only ambiguous case this pipeline actually produces is Phase 4's bare
"digit" markings (OCR can read a numeral with confidence; it has no way to
know on its own whether it's a tuplet number, a fingering, or a rehearsal
mark). Resolution uses only what Phase 5's structure already carries -
measure/beat position of the digit vs. the notes/rests around it:

  - A tight cluster of notes at that beat (2+ notes within half a beat, same
    voice) with the digit exactly "3" is treated as a triplet: the standard
    3-in-the-time-of-2 correction (duration *= 2/3) is applied to that
    cluster. Other tuplet ratios (5, 6, 7, 9 in the time of something other
    than the next-lower power of 2) are NOT handled - reading the true
    ratio needs the bracket/beam grouping this pipeline has no detector for,
    and guessing wrong would silently corrupt durations. Those are left as
    unresolved digits (kept in markings, dropped from playback-affecting
    correction) rather than risk a wrong guess.
  - A single digit 1-5 sitting next to exactly one note, no cluster, is
    treated as a fingering - by far the most common reason a small isolated
    digit appears in real engraving. Fingerings don't affect playback and
    are dropped from the exported markings.
  - Anything else is dropped, not guessed as a rehearsal mark. A real
    rehearsal mark is usually visually boxed/circled and printed in a
    distinct larger font - cues this pipeline has no detector for. Without
    that, an isolated digit is at least as likely to be OCR noise (a
    misread page number, a stray measure-count annotation, a fragment of a
    beam/stem) as a real rehearsal mark; labeling it "rehearsal_mark"
    regardless would put confidently-wrong entries in markings.json, which
    is worse than the honest gap of omitting them.
"""

import logging

_TRIPLET_DIGIT = 3
_CLUSTER_BEAT_WINDOW = 0.5


def _notes_near(notes: list, measure: int, beat: float) -> list:
    return [
        n for n in notes
        if n["measure"] == measure and abs(n["beat"] - beat) <= _CLUSTER_BEAT_WINDOW
    ]


def _resolve_digit(marking: dict, notes: list, logger: logging.Logger) -> "str | None":
    """Returns the resolved marking type, applying any duration correction to
    `notes` in place. Returns None if the digit should be dropped."""
    nearby = _notes_near(notes, marking["measure"], marking["beat"])
    digit = marking["value"]

    if digit == _TRIPLET_DIGIT and len(nearby) >= 2:
        for n in nearby:
            n["duration_ql"] *= 2.0 / 3.0
            n["tuplet_corrected"] = True
        logger.debug(
            "phase6_ambiguity: resolved digit '3' at measure %d beat %.2f as triplet, corrected %d notes",
            marking["measure"], marking["beat"], len(nearby),
        )
        return "tuplet"

    if 1 <= digit <= 5 and len(nearby) == 1:
        return None  # fingering - not a musically meaningful marking, drop it

    return None  # unresolved - see module docstring for why this isn't guessed as a rehearsal mark


def resolve(structure: dict, config, logger: logging.Logger) -> dict:
    notes = structure["notes"]
    resolved_markings = []
    dropped, resolved = 0, 0

    for marking in structure["markings"]:
        if marking["type"] != "digit":
            resolved_markings.append(marking)
            continue

        new_type = _resolve_digit(marking, notes, logger)
        if new_type is None:
            dropped += 1
            continue
        marking["type"] = new_type
        resolved += 1
        resolved_markings.append(marking)

    structure["markings"] = resolved_markings
    logger.info("phase6_ambiguity: resolved %d ambiguous digits as tuplets, dropped %d as fingerings/unresolved", resolved, dropped)
    return structure
