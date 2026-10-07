"""Everything tunable about the arrangement, per style: which transformations run, how the
orchestra is set up, and the effects chain. Plus where the soundfont is and the render rate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_RATE = 48_000  # rendered and final audio stay at this rate
PHRASE_BARS = 4  # the orchestration shapes dynamics and places hits per phrase of this many bars
# Who picks the chords: "builtin" (orchestrate.py; milliseconds, always in key) or "accompanist"
# (accompanist/music/progression.py; about 0.3 s per bar, so 30 s for a 90-bar hum).
HARMONY = "builtin"


# --- General MIDI programs (0-based) and the ranges we write them in ---------------------------

PIANO, VIBRAPHONE = 0, 11
VIOLIN, CELLO, CONTRABASS, PIZZICATO = 40, 42, 43, 45
STRING_ENSEMBLE, SLOW_STRINGS = 48, 49
ACOUSTIC_BASS, FINGER_BASS = 32, 33
STEEL_GUITAR = 25
HARP, TIMPANI = 46, 47
ELECTRIC_PIANO_2, DRAWBAR_ORGAN, ROCK_ORGAN = 5, 16, 18
NYLON_GUITAR, CLEAN_GUITAR, OVERDRIVEN_GUITAR, DISTORTION_GUITAR = 24, 27, 29, 30
PICKED_BASS, SYNTH_BASS_1, SYNTH_BASS_2 = 34, 38, 39
VIOLA, CHOIR, TROMBONE, SYNTH_BRASS, ALTO_SAX, CLARINET = 41, 52, 57, 62, 65, 71
SQUARE_LEAD, SAW_LEAD, CHARANG = 80, 81, 84
WARM_PAD, POLYSYNTH, CHOIR_PAD, SWEEP_PAD, CRYSTAL = 89, 90, 91, 95, 98
# Drum kits (the program on the drum channel; General MIDI 2 / GS numbers, which GeneralUser GS has).
STANDARD_KIT, POWER_KIT, ELECTRONIC_KIT, TR808_KIT, BRUSH_KIT = 0, 16, 24, 25, 40
TRUMPET, FRENCH_HORN, BRASS_SECTION = 56, 60, 61
OBOE, FLUTE = 68, 73

# (lowest, highest) MIDI pitch we write for each instrument: its comfortable range, not the
# extreme one, so nothing sounds strained.
INSTRUMENT_RANGES: dict[int, tuple[int, int]] = {
    PIANO: (36, 96),
    VIBRAPHONE: (53, 89),
    VIOLIN: (55, 100),
    CELLO: (36, 72),
    CONTRABASS: (28, 55),
    PIZZICATO: (36, 84),
    STRING_ENSEMBLE: (43, 81),
    SLOW_STRINGS: (43, 81),
    ACOUSTIC_BASS: (28, 55),
    FINGER_BASS: (28, 55),
    TRUMPET: (55, 82),
    FRENCH_HORN: (41, 77),
    BRASS_SECTION: (46, 77),
    OBOE: (58, 91),
    FLUTE: (60, 96),
    STEEL_GUITAR: (40, 76),
    HARP: (36, 91),
    TIMPANI: (38, 57),
    ELECTRIC_PIANO_2: (40, 88),
    DRAWBAR_ORGAN: (36, 91),
    ROCK_ORGAN: (36, 91),
    NYLON_GUITAR: (40, 79),
    CLEAN_GUITAR: (40, 84),
    OVERDRIVEN_GUITAR: (40, 84),
    DISTORTION_GUITAR: (40, 84),
    PICKED_BASS: (28, 55),
    SYNTH_BASS_1: (28, 58),
    SYNTH_BASS_2: (28, 58),
    VIOLA: (48, 88),
    CHOIR: (48, 79),
    TROMBONE: (40, 72),
    SYNTH_BRASS: (43, 79),
    ALTO_SAX: (49, 81),
    CLARINET: (50, 91),
    SQUARE_LEAD: (55, 91),
    SAW_LEAD: (55, 91),
    CHARANG: (52, 88),
    WARM_PAD: (43, 84),
    POLYSYNTH: (43, 84),
    CHOIR_PAD: (43, 84),
    SWEEP_PAD: (43, 84),
    CRYSTAL: (60, 96),
}

# General MIDI percussion (channel 10) notes used for orchestral hits.
KICK, SNARE, CLOSED_HAT, CRASH, CONCERT_BASS_DRUM = 36, 38, 42, 49, 35
CLAP, OPEN_HAT, RIDE, LOW_TOM, MID_TOM, HIGH_TOM = 39, 46, 51, 45, 47, 50


@dataclass(frozen=True)
class Orchestration:
    lead: int  # the melody's instrument
    pad: int  # sustained strings under it
    bass: int
    brass: int  # swells into phrase peaks
    figure: int  # the moving accompaniment (ostinato, arpeggio, strumming...)
    double: int  # a second instrument on the tune, from the second section on
    figure_pattern: str = "ostinato"  # "ostinato" | "alberti" | "arpeggio" | "comping" | "broken" |
    #                                   "power" (driving power chords) | "arp16" (fast synth arpeggio)
    double_octave: int = 0  # the doubling's octave relative to the lead: -1, 0 or 1
    timpani: bool = False  # timpani on phrase starts and rolling into each peak
    bass_pattern: str = "whole"  # "whole" | "half" | "pulse" (eighths)
    percussion: str = "hits"  # "hits" (downbeat hits, rolls into peaks) | "groove" (backbeat) |
    #                           "rock" (a drum kit with fills into peaks) | "electronic" (four on the
    #                           floor) | "light" (brushes)
    kit: int = STANDARD_KIT  # the drum kit on the drum channel
    dynamics: tuple[int, int] = (58, 104)  # velocity at a phrase's start, and at its peak
    volumes: dict[str, int] = field(
        default_factory=lambda: {"melody": 110, "melody_double": 90, "strings_pad": 70, "figure": 110, "bass": 92,
                                 "brass": 84, "timpani": 92, "percussion": 84}
    )


@dataclass(frozen=True)
class Effects:
    """Pedalboard chain: Compressor -> LowShelfFilter -> Reverb -> Limiter."""

    compressor_threshold_db: float = -18.0
    compressor_ratio: float = 2.5
    compressor_attack_ms: float = 20.0
    compressor_release_ms: float = 200.0
    low_shelf_hz: float = 120.0
    low_shelf_gain_db: float = 2.0
    reverb_room_size: float = 0.7
    reverb_damping: float = 0.45
    reverb_wet: float = 0.25
    reverb_dry: float = 0.8
    reverb_width: float = 1.0
    limiter_threshold_db: float = -1.0
    limiter_release_ms: float = 120.0
    tail_seconds: float = 2.5  # silence added before the reverb so its tail isn't cut off


@dataclass(frozen=True)
class Style:
    transforms: list[tuple[str, dict]]
    orchestration: Orchestration
    effects: Effects
    # The song's shape around the tune (transforms.fill and transforms.frame): a short tune is
    # repeated to at least fill_bars before the style's transformations, then the accompaniment
    # plays intro_bars on its own, building into the tune, and outro_bars let the last chord ring.
    fill_bars: int = 8
    intro_bars: int = 2
    outro_bars: int = 1


STYLES: dict[str, Style] = {
    # Broad and swelling: the tune, then its last phrase an octave higher as the climax.
    "cinematic": Style(
        transforms=[("restate", {"bars": 4, "steps": 7})],
        orchestration=Orchestration(lead=VIOLIN, pad=SLOW_STRINGS, bass=CONTRABASS, brass=BRASS_SECTION,
                                    figure=STRING_ENSEMBLE, figure_pattern="ostinato",
                                    double=FRENCH_HORN, double_octave=-1, timpani=True, bass_pattern="half"),
        effects=Effects(reverb_room_size=0.85, reverb_wet=0.33, reverb_damping=0.4, low_shelf_gain_db=2.5, tail_seconds=3.5),
    ),
    # Minimalist: an additive build-up of the opening bar (arvo), then the tune, over a pulse.
    "modern": Style(
        transforms=[("additive", {"bars": 1})],
        orchestration=Orchestration(lead=VIBRAPHONE, pad=STRING_ENSEMBLE, bass=PIZZICATO, brass=FRENCH_HORN,
                                    figure=PIANO, figure_pattern="arpeggio", double=FLUTE, double_octave=1,
                                    bass_pattern="pulse"),
        effects=Effects(compressor_threshold_db=-20.0, compressor_ratio=3.0, reverb_room_size=0.5, reverb_wet=0.2, low_shelf_gain_db=1.5, tail_seconds=2.0),
        intro_bars=0,  # the additive build-up is its introduction
    ),
    # A rising sequence of the opening figure introduces the tune.
    "classical": Style(
        transforms=[("sequence", {"bars": 1, "steps": [1, 2]})],
        orchestration=Orchestration(lead=FLUTE, pad=STRING_ENSEMBLE, bass=CELLO, brass=FRENCH_HORN,
                                    figure=HARP, figure_pattern="alberti", double=VIOLIN, double_octave=0,
                                    timpani=True, bass_pattern="half", dynamics=(52, 96)),
        effects=Effects(compressor_threshold_db=-16.0, compressor_ratio=1.8, reverb_room_size=0.75, reverb_wet=0.28, reverb_damping=0.5, low_shelf_gain_db=1.0, tail_seconds=3.0),
        intro_bars=1,  # the rising sequence is most of its introduction
    ),
    # Verse twice, with a backbeat.
    "pop": Style(
        transforms=[("repeat", {"times": 2})],
        orchestration=Orchestration(lead=PIANO, pad=STRING_ENSEMBLE, bass=FINGER_BASS, brass=BRASS_SECTION,
                                    figure=STEEL_GUITAR, figure_pattern="comping", double=STRING_ENSEMBLE, double_octave=1,
                                    bass_pattern="pulse", percussion="groove", dynamics=(66, 104)),
        effects=Effects(compressor_threshold_db=-22.0, compressor_ratio=4.0, compressor_attack_ms=10.0, reverb_room_size=0.35, reverb_wet=0.15, low_shelf_hz=90.0, low_shelf_gain_db=3.0, tail_seconds=1.5),
    ),
    # The tune as sung, gently accompanied.
    "piano": Style(
        transforms=[],
        orchestration=Orchestration(lead=PIANO, pad=STRING_ENSEMBLE, bass=CELLO, brass=FRENCH_HORN,
                                    figure=PIANO, figure_pattern="broken", double=STRING_ENSEMBLE, double_octave=0,
                                    dynamics=(50, 88),
                                    volumes={"melody": 115, "melody_double": 75, "strings_pad": 55, "figure": 100,
                                             "bass": 70, "brass": 55, "timpani": 60, "percussion": 60}),
        effects=Effects(compressor_threshold_db=-18.0, compressor_ratio=2.0, reverb_room_size=0.6, reverb_wet=0.22, low_shelf_hz=150.0, low_shelf_gain_db=0.5),
        intro_bars=1,
    ),
}


# Words people (or talk mode) may use for a style, and the style they get. Anything else gets
# DEFAULT_STYLE, with a warning, instead of an error.
DEFAULT_STYLE = "pop"
STYLE_ALIASES: dict[str, str] = {
    "orchestral": "cinematic", "epic": "cinematic", "film": "cinematic", "movie": "cinematic",
    "dramatic": "cinematic", "heroic": "cinematic", "trailer": "cinematic",
    "minimal": "modern", "minimalist": "modern", "lofi": "modern", "lo-fi": "modern",
    "ambient": "modern", "electronic": "modern", "chill": "modern", "jazz": "modern",
    "rock": "pop", "upbeat": "pop", "dance": "pop", "happy": "pop", "funk": "pop",
    "lullaby": "piano", "calm": "piano", "soft": "piano", "gentle": "piano", "sad": "piano",
    "ballad": "piano", "baroque": "classical", "romantic": "classical", "folk": "classical",
    "asian-folk": "classical",
}


def resolve_style(word: str | None) -> tuple[str, str | None]:
    """The style to use for `word`, and a warning when it wasn't one we know."""
    key = (word or "").strip().lower().replace("_", "-").replace(" ", "-")
    if key in STYLES:
        return key, None
    if key in STYLE_ALIASES:
        return STYLE_ALIASES[key], None
    return DEFAULT_STYLE, f"There's no '{word}' style yet, so this was arranged as {DEFAULT_STYLE}."


def get_style(name: str) -> Style:
    try:
        return STYLES[name]
    except KeyError:
        raise ValueError(f"Unknown style {name!r}. Available: {', '.join(sorted(STYLES))}.") from None


# --- soundfont ---------------------------------------------------------------------------------

# Tried in order when SOUNDFONT_PATH isn't set. The last is the tiny synth-like set Homebrew's
# fluid-synth ships: it works, but it doesn't sound orchestral.
_SOUNDFONT_CANDIDATES = [
    Path.home() / "soundfonts" / "GeneralUser-GS.sf2",
    Path.home() / "soundfonts" / "FluidR3_GM.sf2",
    Path(__file__).resolve().parents[2] / "accompanist" / "soundfonts" / "FluidR3_GM.sf2",  # the one the simple engine uses
    Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
    Path("/usr/share/soundfonts/FluidR3_GM.sf2"),
    Path("/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2"),
]


def find_soundfont() -> Path:
    """SOUNDFONT_PATH if set (it must exist), else the first known soundfont on this machine."""
    configured = os.environ.get("SOUNDFONT_PATH")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"SOUNDFONT_PATH points to {path}, which doesn't exist.")
        return path
    for candidate in _SOUNDFONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("No soundfont found. Set SOUNDFONT_PATH to an orchestral .sf2 (e.g. GeneralUser GS).")
