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


# --- dynamics.py --------------------------------------------------------------
#
# Every group is keyed (direction, outcome): outcome "weak" = moved the right
# way but not far enough, "missing" = no audible change or the wrong way.

DYNAMICS_CONTRAST = {  # a new written level, e.g. p -> f. {marking}, {previous}
    ("louder", "weak"): Feedback(
        "The {marking} here was only slightly louder than the {previous} before it.",
        "Exaggerate the change at first: play the {previous} clearly softer and arrive at the {marking} with real weight.",
    ),
    ("louder", "missing"): Feedback(
        "The {marking} here wasn't played louder than the {previous} before it.",
        "Mark the change to {marking} in your mind before you reach it, and play the bars around it slowly, listening for the jump in volume.",
    ),
    ("softer", "weak"): Feedback(
        "The {marking} here was only slightly softer than the {previous} before it.",
        "Exaggerate the change at first: drop right down to the {marking} and keep it there.",
    ),
    ("softer", "missing"): Feedback(
        "The {marking} here wasn't played softer than the {previous} before it.",
        "Mark the change to {marking} in your mind before you reach it, and play the bars around it slowly, listening for the drop in volume.",
    ),
}

DYNAMICS_HAIRPIN = {  # a written crescendo / diminuendo
    ("louder", "weak"): Feedback(
        "The crescendo here only grew slightly.",
        "Start the crescendo softer than feels natural so there is room to grow, and spread the growth evenly to its end.",
    ),
    ("louder", "missing"): Feedback(
        "The crescendo here didn't get louder.",
        "Play this passage slowly and make each note a little louder than the one before it.",
    ),
    ("softer", "weak"): Feedback(
        "The diminuendo here only faded slightly.",
        "Keep letting the sound fall away all the way to the end of the diminuendo instead of levelling off.",
    ),
    ("softer", "missing"): Feedback(
        "The diminuendo here didn't get softer.",
        "Play this passage slowly and make each note a little softer than the one before it.",
    ),
}

DYNAMICS_ACCENT = {  # an accent / sf / sfz note
    ("louder", "weak"): Feedback(
        "This accent was only slightly stronger than the notes around it.",
        "Give the accented note more weight and keep the notes around it lighter so it stands out.",
    ),
    ("louder", "missing"): Feedback(
        "This accent didn't stand out from the notes around it.",
        "Practise this spot slowly, playing the accented note clearly louder than its neighbours.",
    ),
}

DYNAMICS_UNEVEN = {  # an unmarked note that jumps out of the surrounding level
    "louder": Feedback(
        "This note stood out louder than the notes around it.",
        "Play this passage slowly at one steady volume, listening for any note that pokes out.",
    ),
    "softer": Feedback(
        "This note dropped noticeably softer than the notes around it.",
        "Play this passage slowly at one steady volume, making sure this note speaks as fully as its neighbours.",
    ),
}


# --- pedaling.py --------------------------------------------------------------
#
# No entries yet: the judge has no pedal data to comment on (see its module).


# --- phase2/era.py ------------------------------------------------------------
#
# No entries yet: the per-era builders are still unimplemented. Add their
# prose here, e.g. ERA_BAROQUE = {...}, when they are filled in.
