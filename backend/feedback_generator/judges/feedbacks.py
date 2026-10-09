"""Every message and suggestion a judge can emit, in one place.

Judges decide *whether* and *how badly* something went wrong; this module
decides *what the player reads*. Rewording, tone passes, or a future
translation only touch this file -- no detection or scoring code changes.

Each entry is a `Feedback`: a `message` (what happened) and a `suggestion`
(what to practise). Either may hold `str.format` placeholders, filled by
`render(**values)`; the placeholders an entry expects are noted beside it.
Entries are grouped per judge, keyed by the variant the judge detected.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Feedback:
    message: str
    suggestion: str

    def render(self, **values) -> Tuple[str, str]:
        """(message, suggestion) with any placeholders filled from `values`."""
        return self.message.format(**values), self.suggestion.format(**values)


# --- pitch.py -----------------------------------------------------------------

_PITCH_SUGGESTION = "Practice this transition slowly and focus on the correct note."

PITCH_OUT_OF_TUNE = {  # same note name, just off-centre
    "sharp": Feedback("This note was played slightly sharp.", _PITCH_SUGGESTION),
    "flat": Feedback("This note was played slightly flat.", _PITCH_SUGGESTION),
}

PITCH_WRONG_NOTE = Feedback(  # {user_note}, {expected_note}
    "Wrong note — you played {user_note} instead of {expected_note}.",
    _PITCH_SUGGESTION,
)


# --- rhythm.py ----------------------------------------------------------------

_ONSET_SUGGESTION = "Practice this passage with a metronome, focusing on landing the note exactly on the beat."
_DURATION_SUGGESTION = "Slow down and count out this note's full written duration before returning to full tempo."

RHYTHM_ONSET = {
    "late": Feedback("This note came in late, disrupting the rhythm.", _ONSET_SUGGESTION),
    "early": Feedback("This note came in early, disrupting the rhythm.", _ONSET_SUGGESTION),
}

RHYTHM_DURATION = {
    "too_long": Feedback("This note was held longer than written.", _DURATION_SUGGESTION),
    "too_short": Feedback("This note was cut short compared to what's written.", _DURATION_SUGGESTION),
}


# --- tempo.py -----------------------------------------------------------------

_TEMPO_SUGGESTION = "Practice the phrase with a metronome, paying close attention to keeping a steady tempo through to the end."

TEMPO_DRIFT = {
    "slowing": Feedback("The tempo gradually slows down across the phrase.", _TEMPO_SUGGESTION),
    "rushing": Feedback("The tempo gradually rushes across the phrase.", _TEMPO_SUGGESTION),
}


# --- articulation.py ----------------------------------------------------------
#
# Keyed by the marking from articulation.ARTICULATION_WORDS -- a new word
# there needs an entry here.

ARTICULATION = {
    "staccato": Feedback(
        "This note was held too long for the marked staccato articulation.",
        "Practice this note in isolation with the marked staccato articulation before returning to full tempo.",
    ),
    "legato": Feedback(
        "This note was cut short for the marked legato articulation.",
        "Practice this note in isolation with the marked legato articulation before returning to full tempo.",
    ),
    "marcato": Feedback(
        "This note was cut short for the marked marcato articulation.",
        "Practice this note in isolation with the marked marcato articulation before returning to full tempo.",
    ),
}


# --- notes.py -----------------------------------------------------------------

NOTES_MISSING = Feedback(
    "This note was not played.",
    "Go through this passage slowly, note-by-note, to make sure this note is included.",
)

NOTES_EXTRA = Feedback(
    "An extra note was played that isn't in the score.",
    "Review the written notes here closely and avoid adding notes that aren't written.",
)


# --- dynamics.py / pedaling.py ------------------------------------------------
#
# No entries yet: neither judge has data to comment on (see their modules).


# --- phase2/era.py ------------------------------------------------------------
#
# No entries yet: the per-era builders are still unimplemented. Add their
# prose here, e.g. ERA_BAROQUE = {...}, when they are filled in.
