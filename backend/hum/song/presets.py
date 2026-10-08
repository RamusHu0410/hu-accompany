"""Genres and moods: what the band sounds like.

Each genre is a small, fixed band that belongs together (lofi is a Rhodes, a sub bass and soft
swung drums), the rhythms its players use, the chord progressions it leans on, and the tempos it
lives at. A mood shades any genre: darker or brighter chords, calmer or busier playing, a little
slower or faster. Programs are General MIDI; drum kits are the GM kit numbers (FluidR3 has them all).
"""

from dataclasses import dataclass

# GM drum kits
STANDARD_KIT, ROOM_KIT, POWER_KIT, ELECTRONIC_KIT, TR808_KIT, JAZZ_KIT, BRUSH_KIT, ORCHESTRA_KIT = 0, 8, 16, 24, 25, 32, 40, 48


@dataclass(frozen=True)
class Palette:
    melody: int
    chords: int
    bass: int
    pad: int | None  # None: this genre has no pad unless the mood asks for one
    drums: int  # drum kit


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    palette: Palette
    tempo_range: tuple[float, float]
    swing: float  # 0.5 straight
    comping: str  # how the chords are played in a full section (parts.COMPING)
    comping_light: str  # and in a light one
    bass: str  # parts.BASS_LINES, full section
    bass_light: str
    groove: str  # drums.GROOVES
    progressions: dict  # mode -> degree sequences the chords lean toward
    sevenths: bool = False
    power_chords: bool = False
    intro_bars: int = 2
    intro_intensity: int = 0  # drums in the intro: 0 none, 1 light
    reverb: float = 0.2


POP_MAJOR = (("I", "V", "vi", "IV"), ("I", "vi", "IV", "V"), ("vi", "IV", "I", "V"))
POP_MINOR = (("i", "VI", "III", "VII"), ("i", "iv", "VI", "V"), ("i", "VII", "VI", "VII"))

PRESETS: dict[str, Preset] = {
    p.id: p
    for p in (
        Preset("pop", "Pop", Palette(81, 0, 33, 89, STANDARD_KIT), (90, 124), 0.5,
               "pulse", "hold", "root_fifth", "hold", "pop",
               {"major": POP_MAJOR, "minor": POP_MINOR}),
        Preset("lofi", "Lo-fi", Palette(11, 4, 38, None, ROOM_KIT), (70, 90), 0.6,
               "lofi", "hold", "lofi", "hold", "lofi",
               {"major": (("ii", "V", "I", "vi"), ("IV", "iii", "ii", "I")), "minor": (("i", "iv", "VII", "III"), ("i", "VI", "iv", "V"))},
               sevenths=True, intro_intensity=1, reverb=0.3),
        Preset("rock", "Rock", Palette(29, 30, 34, None, POWER_KIT), (100, 150), 0.5,
               "power8", "power_hold", "eighths", "root_fifth", "rock",
               {"major": (("I", "IV", "V", "IV"), ("I", "V", "IV", "IV")), "minor": (("i", "VI", "VII", "i"), ("i", "VII", "VI", "VII"))},
               power_chords=True, reverb=0.12),
        Preset("ballad", "Ballad", Palette(0, 48, 42, None, BRUSH_KIT), (60, 84), 0.5,
               "hold", "hold", "hold", "hold", "ballad",
               {"major": (("I", "vi", "IV", "V"), ("I", "iii", "IV", "V")), "minor": (("i", "VI", "iv", "V"),)},
               intro_bars=4, reverb=0.35),
        Preset("cinematic", "Cinematic", Palette(60, 48, 42, 52, ORCHESTRA_KIT), (70, 110), 0.5,
               "arp", "hold", "hold", "hold", "cinematic",
               {"major": (("I", "V", "vi", "IV"), ("vi", "IV", "I", "V")), "minor": (("i", "VI", "III", "VII"), ("i", "VI", "iv", "V"))},
               intro_bars=4, reverb=0.4),
        Preset("electronic", "Electronic", Palette(81, 90, 38, 89, ELECTRONIC_KIT), (118, 130), 0.5,
               "stab", "hold", "offbeat", "hold", "electronic",
               {"major": POP_MAJOR, "minor": (("i", "VI", "III", "VII"), ("i", "VII", "VI", "VII"))},
               intro_intensity=1, reverb=0.2),
        Preset("jazz", "Jazz", Palette(65, 0, 32, None, JAZZ_KIT), (90, 140), 0.64,
               "charleston", "hold", "walking", "root_fifth", "jazz",
               {"major": (("ii", "V", "I", "vi"), ("I", "vi", "ii", "V")), "minor": (("i", "iv", "V", "i"), ("i", "VI", "iv", "V"))},
               sevenths=True, reverb=0.22),
        Preset("acoustic", "Acoustic", Palette(73, 25, 32, None, STANDARD_KIT), (80, 120), 0.5,
               "strum", "hold", "root_fifth", "hold", "acoustic",
               {"major": (("I", "IV", "I", "V"), ("I", "V", "vi", "IV")), "minor": (("i", "VII", "VI", "VII"), ("i", "iv", "i", "V"))},
               reverb=0.25),
    )
}
DEFAULT_PRESET = "pop"

# Words people (and the app's older settings) use for a genre.
PRESET_ALIASES = {
    "lo-fi": "lofi", "lo fi": "lofi", "chill": "lofi", "chillhop": "lofi",
    "orchestral": "cinematic", "orchestra": "cinematic", "epic": "cinematic", "film": "cinematic",
    "edm": "electronic", "dance": "electronic", "house": "electronic", "synthwave": "electronic",
    "piano": "ballad", "slow": "ballad", "folk": "acoustic", "guitar": "acoustic",
    "swing": "jazz", "metal": "rock", "punk": "rock",
}


@dataclass(frozen=True)
class Mood:
    id: str
    label: str
    tempo_factor: float = 1.0
    intensity_shift: int = 0  # added to the verse's and chorus's intensity
    velocity_shift: int = 0
    chord_lean: str | None = None  # "minor" or "major": which chords win when the tune allows either
    reverb_add: float = 0.0
    brightness_db: float = 0.0  # high shelf on every track
    pad: bool = False  # bring in a pad even when the genre has none


MOODS: dict[str, Mood] = {
    m.id: m
    for m in (
        Mood("neutral", "As hummed"),
        Mood("dark", "Dark", tempo_factor=0.96, velocity_shift=-8, chord_lean="minor", reverb_add=0.1, brightness_db=-3, pad=True),
        Mood("chill", "Chill", tempo_factor=0.94, intensity_shift=-1, velocity_shift=-12, reverb_add=0.12, brightness_db=-2),
        Mood("bright", "Bright", tempo_factor=1.03, chord_lean="major", brightness_db=2),
        Mood("hype", "Hype", tempo_factor=1.06, intensity_shift=1, velocity_shift=10, brightness_db=1),
    )
}
DEFAULT_MOOD = "neutral"

MAX_TEMPO_NUDGE = 0.12  # a genre may pull the hum's tempo this far toward its own range


def preset_for(word: str | None) -> Preset:
    """The genre a word names; the default for an unknown or missing one."""
    key = (word or "").strip().lower()
    return PRESETS.get(PRESET_ALIASES.get(key, key), PRESETS[DEFAULT_PRESET])


def mood_for(word: str | None) -> Mood:
    return MOODS.get((word or "").strip().lower(), MOODS[DEFAULT_MOOD])


def feel_tempo(hum_tempo: float, preset: Preset, mood: Mood, speed: float = 1.0) -> tuple[float, float]:
    """The song's tempo and how the hum's beats map onto it (1, or 2 when the genre plays the
    tune in double time, 0.5 in half time). The tune keeps its speed in seconds unless it has to
    move: then it's nudged toward the genre's range (at most MAX_TEMPO_NUDGE). The mood and the
    speed setting scale the result."""
    low, high = preset.tempo_range
    best = None
    for beats in (1.0, 2.0, 0.5):
        tempo = hum_tempo * beats
        nearest = min(max(tempo, low), high)
        miss = abs(nearest / tempo - 1)
        if best is None or miss < best[0] - 1e-9:
            best = (miss, beats, tempo, nearest)
    _, beats, tempo, nearest = best
    nudged = min(max(nearest, tempo * (1 - MAX_TEMPO_NUDGE)), tempo * (1 + MAX_TEMPO_NUDGE))
    return round(nudged * mood.tempo_factor * speed, 1), beats
