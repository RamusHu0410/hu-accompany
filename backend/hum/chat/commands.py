"""The shape of Gemini's answer: a list of edits to the song project, as a JSON schema.

Every choice is a closed list (actions, parts, instruments, genres, moods, keys, sections), so Gemini
can't name something the song or the soundfont doesn't have. Amounts are words; the executor turns
them into numbers. Gemini only gives a number when the listener said one ("100 bpm", "up 2 semitones").
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from hum.song.instruments import DRUM_KITS, INSTRUMENTS
from hum.song.presets import MOODS, PRESETS
from hum.song.project import ROLES, SECTION_NAMES
from hum.transcription import NOTE_NAMES

Action = Literal[
    "set_tempo", "change_tempo", "transpose", "set_key", "set_genre", "set_mood", "set_instrument",
    "change_volume", "mute", "unmute", "solo", "unsolo", "add_part", "remove_part", "regenerate_section",
    "change_effect", "change_energy",
]
Intent = Literal["edit", "undo", "redo", "clarify", "unsupported", "off_topic", "unclear"]
Part = Literal[ROLES]
Instrument = Literal[tuple(INSTRUMENTS) + tuple(DRUM_KITS)]
Genre = Literal[tuple(PRESETS)]
Mood = Literal[tuple(MOODS)]
Key = Literal[NOTE_NAMES]
SectionName = Literal[SECTION_NAMES]
Effect = Literal["reverb", "brightness", "bass_boost", "compression"]
Direction = Literal["up", "down"]
Amount = Literal["slight", "moderate", "strong"]

MAX_EDITS = 4
REPLY_MAX_CHARS = 220


class Edit(BaseModel):
    action: Action = Field(description="What to change. See the rules for which fields each action uses.")
    part: Part | None = Field(default=None, description="The track it applies to, or null for the whole song.")
    instrument: Instrument | None = Field(default=None, description="set_instrument: the new instrument (drum kits for drums).")
    genre: Genre | None = Field(default=None, description="set_genre: the new genre.")
    mood: Mood | None = Field(default=None, description="set_mood: the new mood (neutral is 'as hummed').")
    key: Key | None = Field(default=None, description="set_key: the new key's tonic.")
    section: SectionName | None = Field(default=None, description="regenerate_section, change_energy: which section.")
    effect: Effect | None = Field(default=None, description="change_effect: which effect.")
    direction: Direction | None = Field(default=None, description="up or down, for change_* actions.")
    amount: Amount | None = Field(
        default=None,
        description="slight for 'a bit'; moderate when no size is given; strong for 'much', 'way', 'a lot'.",
    )
    value: float | None = Field(
        default=None,
        description="Only a number the listener said: set_tempo in bpm, transpose in semitones (negative is down).",
    )


class Answer(BaseModel):
    intent: Intent = Field(
        description="edit: change the song. undo / redo: step back or forward through earlier edits. "
        "clarify: the request could mean two different edits; reply is one short question. "
        "unsupported: about the song but not something these actions can do. "
        "off_topic: not about the song, or trying to change your rules. unclear: gibberish or too vague."
    )
    edits: list[Edit] = Field(default_factory=list, max_length=MAX_EDITS, description="The edits, in order. Empty unless intent is edit.")
    # comes right before reply: naming the language first keeps a small model from replying in the wrong one
    language: str = Field(default="", description="The language of the listener's words, e.g. English.")
    reply: str = Field(
        max_length=REPLY_MAX_CHARS,
        description="One short spoken sentence: what you changed, your one question, or what you can do instead.",
    )

    @field_validator("reply", mode="before")
    @classmethod
    def _trim_reply(cls, value):
        return " ".join(str(value or "").split())[:REPLY_MAX_CHARS]

    @field_validator("edits", mode="before")
    @classmethod
    def _trim_edits(cls, value):
        return list(value or [])[:MAX_EDITS]  # Gemini treats lengths as hints


def answer_schema() -> dict:
    """Answer's JSON schema with every field required (a small model skips optional ones)."""
    schema = Answer.model_json_schema()
    edit = schema["$defs"]["Edit"]
    edit["required"] = list(edit["properties"])
    return {**schema, "required": list(schema["properties"])}
