"""The song's settings and the plain arithmetic that changes them.

Same three dials as the main app's "Your song" panel (useSongSettings.ts): each runs from
0 (moody / slower / lower) to 1 (bright / faster / higher), with 0.5 in the middle.
Gemini only says which way and how much; the numbers are always worked out here.

The song also has a short list of instruments. Exactly one is the lead: it plays the tune
and the chords over the whole song. The others play softly underneath (see song.py).
energy makes the first or the second half calmer (below 0) or bigger (above 0).
"""

import math
import re
from dataclasses import asdict, dataclass, replace

from .commands import Adjustment, Change, Command, Energy

DIALS = ("emotion", "speed", "pitch")
MIDDLE = 0.5
STEPS = {"slight": 0.1, "moderate": 0.2, "strong": 0.35}
ROLES = ("lead", "background")
LEVELS = ("soft", "normal", "loud")  # quietest first
SECTIONS = ("all", "start", "end")
DRUMS = "drums"  # plays a beat, so it can never carry the tune
MAX_INSTRUMENTS = 6
MAX_ENERGY = 2
LABEL_PATTERN = re.compile(r"[a-z0-9][a-z0-9 &'-]{0,23}")


@dataclass(frozen=True)
class Part:
    """One instrument in the song."""

    name: str
    role: str = "background"  # lead: plays the tune and the chords. background: plays softly underneath
    level: str = "soft"
    section: str = "all"  # where it plays: all, start (the first half) or end (the second half)


PIANO = Part("piano", "lead", "normal")
SYNTH = Part("synth", "lead", "normal")
DEFAULT_LEAD = SYNTH


@dataclass(frozen=True)
class SongSettings:
    emotion: float = MIDDLE
    speed: float = MIDDLE
    pitch: float = MIDDLE
    style: str | None = None
    instruments: tuple[Part, ...] = (DEFAULT_LEAD,)
    energy: tuple[int, int] = (0, 0)  # the first half and the second half

    @classmethod
    def from_dict(cls, data: dict | None) -> "SongSettings":
        """Reads settings sent by the page. Raises ValueError when they aren't usable."""
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("settings must be an object")
        dials = {name: _read_dial(data.get(name, MIDDLE), name) for name in DIALS}
        style = data.get("style")
        return cls(
            **dials,
            style=clean_label(style) if style else None,
            instruments=_read_instruments(data.get("instruments")),
            energy=_read_energy(data.get("energy")),
        )

    def to_dict(self) -> dict:
        return {
            "emotion": self.emotion,
            "speed": self.speed,
            "pitch": self.pitch,
            "style": self.style,
            "instruments": [asdict(part) for part in self.instruments],
            "energy": {"start": self.energy[0], "end": self.energy[1]},
        }


def clean_label(text) -> str | None:
    """A short lowercase label like 'rock' or 'lo-fi', or None if it isn't one."""
    if not isinstance(text, str):
        return None
    label = " ".join(text.lower().split())
    return label if LABEL_PATTERN.fullmatch(label) else None


def move_dial(value: float, direction: str, amount: str) -> float:
    if direction == "reset":
        return MIDDLE
    if amount == "max":
        return 1.0 if direction == "up" else 0.0
    step = STEPS[amount] if direction == "up" else -STEPS[amount]
    return round(min(1.0, max(0.0, value + step)), 2)


def apply_command(settings: SongSettings, command: Command) -> SongSettings:
    """The settings after Gemini's changes, once edits.check has made them safe."""
    dials = {name: getattr(settings, name) for name in DIALS}
    for change in command.adjustments:
        dials[change.setting] = move_dial(dials[change.setting], change.direction, change.amount)
    style = clean_label(command.style) or settings.style
    instruments = edit_instruments(settings.instruments, command)
    return replace(settings, **dials, style=style, instruments=instruments, energy=move_energy(settings.energy, command.energy))


def edit_instruments(parts: tuple[Part, ...], command: Command) -> tuple[Part, ...]:
    """Removals and swaps first, then changes, then additions. The names were checked by edits.check."""
    swaps = {swap.old: swap.new for swap in command.replace}
    parts = [replace(part, name=swaps.get(part.name, part.name)) for part in parts if part.name not in command.remove]
    wanted = None  # an instrument asked to take the lead
    for change in command.change:
        parts = [_changed(part, change) if part.name == change.instrument else part for part in parts]
        wanted = change.instrument if change.lead else wanted
    for new in command.add:
        if new.instrument not in [part.name for part in parts]:
            parts.append(Part(new.instrument, new.role, new.level, new.section))
            wanted = new.instrument if new.role == "lead" else wanted
    return with_one_lead(parts[:MAX_INSTRUMENTS], wanted)


def with_one_lead(parts, wanted: str | None = None) -> tuple[Part, ...]:
    """Exactly one lead, playing the whole song: the one just asked for, else the current lead, else
    the first instrument that can carry a tune. Nothing left that can? The default synth returns as lead."""
    names = [part.name for part in parts]
    current = next((part.name for part in parts if part.role == "lead" and part.name != DRUMS), None)
    lead = wanted if wanted in names else current or next((name for name in names if name != DRUMS), None)
    if lead is None:
        return (DEFAULT_LEAD, *(replace(part, role="background") for part in parts))
    return tuple(replace(part, role="lead", section="all") if part.name == lead else replace(part, role="background") for part in parts)


def move_energy(energy: tuple[int, int], moves: list[Energy]) -> tuple[int, int]:
    start, end = energy
    for move in moves:
        step = 1 if move.direction == "up" else -1
        if move.section == "start":
            start = max(-MAX_ENERGY, min(MAX_ENERGY, start + step))
        else:
            end = max(-MAX_ENERGY, min(MAX_ENERGY, end + step))
    return start, end


def changed_fields(before: SongSettings, after: SongSettings) -> list[str]:
    return [name for name in (*DIALS, "style", "instruments", "energy") if getattr(before, name) != getattr(after, name)]


def blocked_adjustments(before: SongSettings, command: Command) -> list[Adjustment]:
    """Changes that did nothing because the dial was already at that end (or already normal)."""
    return [c for c in command.adjustments if move_dial(getattr(before, c.setting), c.direction, c.amount) == getattr(before, c.setting)]


def _changed(part: Part, change: Change) -> Part:
    step = {"softer": -1, "louder": 1}.get(change.level, 0)
    level = LEVELS[max(0, min(len(LEVELS) - 1, LEVELS.index(part.level) + step))]
    return replace(part, level=level, section=change.section or part.section)


def _read_dial(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number from 0 to 1")
    return round(min(1.0, max(0.0, float(value))), 2)


def _read_instruments(data) -> tuple[Part, ...]:
    """The page's instrument list, as the server last sent it."""
    if data is None:
        return (DEFAULT_LEAD,)
    if not isinstance(data, list):
        raise ValueError("instruments must be a list")
    parts = []
    for item in data[:MAX_INSTRUMENTS]:
        part = Part(**{key: item.get(key) for key in ("name", "role", "level", "section")}) if isinstance(item, dict) else None
        if part is None or clean_label(part.name) != part.name or part.role not in ROLES or part.level not in LEVELS or part.section not in SECTIONS:
            raise ValueError("each instrument needs a name, a role (lead or background), a level (soft, normal or loud) and a section (all, start or end)")
        if part.name not in [p.name for p in parts]:
            parts.append(part)
    return with_one_lead(parts)


def _read_energy(data) -> tuple[int, int]:
    """The page's {start, end}: whole numbers from -2 (calmest) to 2 (biggest)."""
    data = {} if data is None else data
    halves = (data.get("start", 0), data.get("end", 0)) if isinstance(data, dict) else (None, None)
    if not all(isinstance(step, int) and not isinstance(step, bool) and abs(step) <= MAX_ENERGY for step in halves):
        raise ValueError(f"energy must be {{start, end}}, whole numbers from -{MAX_ENERGY} to {MAX_ENERGY}")
    return halves
