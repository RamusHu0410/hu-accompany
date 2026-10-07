"""Checks Gemini's edit before it touches the song, so an edit can't undo what nobody asked to change.

    what they said → Gemini's edit → check() → apply_command() → the song is remade

Keeping things is the default. check() drops or softens whatever the listener's words don't back
up, and returns notes on what it corrected, so the spoken reply stays honest:

1. Only instruments ECKO has a sound for can come in; only instruments in the song can change.
2. Whatever Gemini itself put in keep can't be taken out, swapped, or moved to one half.
3. Taking out or swapping needs words that ask for it (remove, take out, instead, replace…).
   Without them a removal is dropped and a swap becomes an addition, so "add violin behind the
   piano" can never lose the piano. The words are English and Spanish.
4. A new instrument joins in the background unless the listener asked for a lead (lead, melody,
   tune…). Drums never lead.
5. Something must carry the tune, so the last instrument that can isn't taken out.

describe() then says what the edit did, one line per instrument, for the page to show.
"""

import re
import unicodedata

from . import phrases
from .commands import Change, Command, NewInstrument, Swap
from .settings import DRUMS, LEVELS, Part, SongSettings, clean_label
from .song import instrument_name

# In the listener's words, lowercased and without accents
ASKS_TO_REMOVE = re.compile(
    r"\b(remov|take .*\b(out|off|away)\b|get rid|without\b|no more\b|drop|delet|lose\b|mute|cut\b|replac|swap|switch|instead\b"
    r"|rather than\b|chang|turn .* into\b|only\b|just\b|quit(a|ar|ale|alo|en)\b|sac(a|ar|ale|alo)\b|elimin|sin\b|reemplaz|cambi"
    r"|en vez\b|en lugar\b)"
)
ASKS_FOR_A_LEAD = re.compile(r"\b(lead|main\b|melod|tune\b|solo|front\b|take over|carr(y|ies)\b|principal|protagonista)")
SECTION_WORDS = {"all": "whole song", "start": "first half only", "end": "second half only"}


def check(command: Command, current: SongSettings, heard: str) -> tuple[Command, list[str]]:
    """Gemini's edit without anything the listener didn't ask for, and notes on what was corrected."""
    said = _plain(heard)
    may_remove, may_lead = bool(ASKS_TO_REMOVE.search(said)), bool(ASKS_FOR_A_LEAD.search(said))
    in_song = {part.name: part for part in current.instruments}
    kept = {instrument_name(word) for word in command.keep}
    notes: list[str] = []
    add: list[NewInstrument] = []
    remove: list[str] = []
    swaps: list[Swap] = []
    change: list[Change] = []

    for new in command.add:
        name = instrument_name(new.instrument)
        if name is None:
            notes += _note(phrases.no_sound_for, new.instrument)
        elif name not in in_song:
            lead = new.role == "lead" and may_lead and name != DRUMS
            add.append(new.model_copy(update={"instrument": name, "role": "lead" if lead else "background"}))

    for swap in command.replace:
        old, new = instrument_name(swap.old), instrument_name(swap.new)
        if old not in in_song or new is None:
            notes += _note(phrases.not_in_song, swap.old) if new else _note(phrases.no_sound_for, swap.new)
        elif old in kept or not may_remove or (new == DRUMS and in_song[old].role == "lead"):
            notes.append(phrases.drums_underneath(old) if new == DRUMS else phrases.kept(old))
            if new not in in_song:
                add.append(NewInstrument(instrument=new))  # it joins in the background instead
        elif new in in_song:  # both play already: the old one goes, and the new one takes over its role
            remove.append(old)
            change.append(Change(instrument=new, lead=in_song[old].role == "lead"))
        else:
            swaps.append(Swap(old=old, new=new))

    for word in command.remove:
        name = instrument_name(word)
        if name not in in_song:
            notes += _note(phrases.not_in_song, word)
        elif name in kept or not may_remove:
            notes.append(phrases.kept(name))
        else:
            remove.append(name)

    for asked in command.change:
        name = instrument_name(asked.instrument)
        if name not in in_song:
            notes += _note(phrases.not_in_song, asked.instrument)
        else:
            lead = asked.lead and may_lead and name != DRUMS
            change.append(asked.model_copy(update={"instrument": name, "lead": lead, "section": None if name in kept else asked.section}))

    renamed = {swap.old: swap.new for swap in swaps}
    left = [renamed.get(name, name) for name in in_song if name not in remove] + [new.instrument for new in add]
    if all(name == DRUMS for name in left):  # nothing would carry the tune
        notes += [phrases.carries_the_tune(name) for name in remove if name != DRUMS]
        remove = [name for name in remove if name == DRUMS]

    return command.model_copy(update={"add": add, "remove": remove, "replace": swaps, "change": change}), notes


def describe(before: SongSettings, after: SongSettings) -> list[str]:
    """What an edit did to the song, for the page: ✓ kept, + added, − taken out, ~ changed.
    Empty when only the dials moved, since the faders show that."""
    if (before.instruments, before.energy, before.style) == (after.instruments, after.energy, after.style):
        return []
    old = {part.name: part for part in before.instruments}
    lines = []
    for part in after.instruments:
        if part.name not in old:
            lines.append(f"+ Add {part.name} — {_how(part)}")
        elif part == old[part.name]:
            lines.append(f"✓ Keep {part.name}")
        else:
            lines.append(f"~ {part.name.capitalize()}: {_what_changed(old[part.name], part)}")
    lines += [f"− Remove {name}" for name in old if name not in [part.name for part in after.instruments]]
    for half, word in enumerate(("First half", "Second half")):
        if after.energy[half] != before.energy[half]:
            lines.append(f"~ {word}: {'bigger' if after.energy[half] > before.energy[half] else 'calmer'}")
    if after.style != before.style:
        lines.append(f"~ Style: {after.style}")
    return lines


def _how(part: Part) -> str:
    """e.g. 'plays the tune', or 'soft, in the background, second half only'."""
    if part.role == "lead":
        return "plays the tune"
    return ", ".join([part.level, "in the background"] + ([SECTION_WORDS[part.section]] if part.section != "all" else []))


def _what_changed(old: Part, new: Part) -> str:
    changes = []
    if new.level != old.level:
        changes.append("louder" if LEVELS.index(new.level) > LEVELS.index(old.level) else "softer")
    if new.role != old.role:
        changes.append("plays the tune" if new.role == "lead" else "moves to the background")
    if new.section != old.section:
        changes.append(SECTION_WORDS[new.section])
    return ", ".join(changes)


def _note(phrase, word) -> list[str]:
    """A note naming what Gemini wrote, only if it's a plain label: the note is spoken out loud."""
    label = clean_label(word)
    return [phrase(label)] if label else []


def _plain(text: str) -> str:
    """Lowercase without accents, so 'Quítale el violín' reads 'quitale el violin'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
