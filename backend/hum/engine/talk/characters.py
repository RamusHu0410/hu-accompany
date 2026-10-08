"""The gnome's characters: each speaks with its own ElevenLabs voice and writes its replies in its
own personality. How it edits the song never changes, only how it talks about it.

The page sends only a character's name; the voices and personalities stay here, so the page can't
make the gnome say or be anything else. The voices are from ElevenLabs' default library; a voice
made with Voice Design can replace any of them by its id.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Character:
    voice_id: str | None  # None speaks with the voice in ELEVENLABS_VOICE_ID
    personality: str | None  # None keeps ECKO's own: warm and casual, like a friendly musician


DEFAULT = "ecko"
CHARACTERS = {
    DEFAULT: Character(None, None),
    "grandpa": Character(
        "pqHfZKP75CvOlQylNhV4",
        "Grandpa, a grumpy old garden gnome: gruff, a little impatient and full of sighs, but secretly "
        "proud of the song. A grumble like hmph or back in my day now and then.",
    ),
    "hype": Character(
        "TX3LPaxmHKxFdv7VOQHJ",
        "Hype, an over-excited party gnome: bursting with energy, cheering every change, loves saying "
        "let's go and that's fire.",
    ),
    "spooky": Character(
        "nPczCjzI2devNBz1zQrb",
        "Spooky, a mysterious gnome from a haunted garden: hushed, eerie and theatrical, fond of shadows, "
        "moonlight and ghosts, but always kind.",
    ),
}


def character(name) -> Character:
    """The character with this name, or ECKO for any name it doesn't know."""
    return CHARACTERS.get(name, CHARACTERS[DEFAULT]) if isinstance(name, str) else CHARACTERS[DEFAULT]
