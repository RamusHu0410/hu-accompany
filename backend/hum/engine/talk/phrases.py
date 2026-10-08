"""Every fixed sentence the voice can say when Gemini isn't asked, can't answer, or its edit was corrected."""

from .commands import Adjustment

NOTHING_TYPED = "I didn't catch anything there. Tell me how you'd like the song to change, like faster or brighter."
NOTHING_HEARD = "I couldn't hear you that time. Hold the button and tell me how to change the song."
NOTHING_TO_UNDO = "There's nothing to undo yet. This is the first version of your song."
LOST_THOUGHT = "Sorry, I lost my train of thought. Could you say that again?"
EARS_FAILED = "Sorry, I couldn't make out that recording. Could you try once more?"
UNDONE = "Okay, I put the song back the way it was."
DONE = "Done! Have a listen and tell me what you think."
OFF_TOPIC = "I'm here to help with your song. Try something like make it faster, or turn it into jazz."
NOTHING_CHANGED = "The song already sounds like that. Want to try something else, like a new style?"

_ALREADY = {
    ("emotion", "up"): "as bright as it goes",
    ("emotion", "down"): "as moody as it goes",
    ("speed", "up"): "as fast as it goes",
    ("speed", "down"): "as slow as it goes",
    ("pitch", "up"): "as high as it goes",
    ("pitch", "down"): "as low as it goes",
}
_NAMES = {"emotion": "The emotion", "speed": "The speed", "pitch": "The pitch"}


def already_there(blocked: list[Adjustment]) -> str:
    """For a change that couldn't happen, e.g. 'It's already as fast as it goes.'"""
    if not blocked:
        return NOTHING_CHANGED
    first = blocked[0]
    if first.direction == "reset":
        return f"{_NAMES[first.setting]} is already back to normal. Anything else you'd like to change?"
    return f"It's already {_ALREADY[(first.setting, first.direction)]}. Anything else you'd like to change?"


# When edits.check corrects Gemini's edit, these replace its reply, which described the uncorrected edit.
def done_but(notes: list[str]) -> str:
    return "Done! " + " ".join(notes)


def kept(name: str) -> str:
    return f"I kept the {name}, since you didn't ask to take it out."


def drums_underneath(name: str) -> str:
    return f"Drums can't carry your tune, so I kept the {name} and put the drums underneath."


def carries_the_tune(name: str) -> str:
    return f"The {name} is carrying your tune, so I kept it. You could swap it for another instrument instead."


def not_in_song(name: str) -> str:
    return f"I can't find the {name} in your song."


def no_sound_for(name: str) -> str:
    return f"I don't have a sound for {name} yet."
