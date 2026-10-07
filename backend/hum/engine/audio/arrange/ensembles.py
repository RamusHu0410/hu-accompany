"""Which band plays the song: an orchestra, a rock band, electronic instruments or a small acoustic
group, and within each, which instruments exactly.

A style (config.STYLES) decides what happens to the tune and how it's mixed; an ensemble decides who
plays it. Without a variation, a style keeps its own orchestra (config.STYLES[...].orchestration).
With one (a seed), `choose` picks an ensemble and an instrument for every role, so each new song can
sound different, while the same seed always gives the same combination: a listener tweaking one song
keeps its sound.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from . import config as c
from .config import Orchestration, Style

# (program, octave relative to the lead) for the instrument doubling the tune
Double = tuple[int, int]
# (program, pattern) for the moving accompaniment
Figure = tuple[int, str]


@dataclass(frozen=True)
class Ensemble:
    leads: tuple[int, ...]
    doubles: tuple[Double, ...]
    pads: tuple[int, ...]
    figures: tuple[Figure, ...]
    basses: tuple[int, ...]
    bass_patterns: tuple[str, ...]
    swells: tuple[int, ...]  # the instrument that swells into each peak (the orchestra's brass)
    kits: tuple[int, ...]
    percussion: str
    timpani: bool
    volumes: dict[str, int]
    reverb_scale: float = 1.0  # how much of the style's reverb this ensemble takes


ENSEMBLES: dict[str, Ensemble] = {
    "orchestra": Ensemble(
        leads=(c.VIOLIN, c.FLUTE, c.FRENCH_HORN, c.OBOE),
        doubles=((c.FRENCH_HORN, -1), (c.CELLO, -1), (c.VIOLIN, 0), (c.FLUTE, 1)),
        pads=(c.SLOW_STRINGS, c.STRING_ENSEMBLE, c.CHOIR),
        figures=((c.STRING_ENSEMBLE, "ostinato"), (c.HARP, "alberti"), (c.PIZZICATO, "ostinato"), (c.HARP, "arpeggio")),
        basses=(c.CONTRABASS, c.CELLO),
        bass_patterns=("half", "whole"),
        swells=(c.BRASS_SECTION, c.FRENCH_HORN, c.TROMBONE),
        kits=(c.STANDARD_KIT,),
        percussion="hits",
        timpani=True,
        volumes={"melody": 110, "melody_double": 90, "strings_pad": 70, "figure": 110, "bass": 92,
                 "brass": 84, "timpani": 92, "percussion": 84},
        reverb_scale=1.1,
    ),
    "band": Ensemble(
        leads=(c.OVERDRIVEN_GUITAR, c.ROCK_ORGAN, c.ALTO_SAX, c.CLEAN_GUITAR),
        doubles=((c.DISTORTION_GUITAR, -1), (c.ROCK_ORGAN, 0), (c.ALTO_SAX, 0), (c.CLEAN_GUITAR, 1)),
        pads=(c.DRAWBAR_ORGAN, c.WARM_PAD, c.STRING_ENSEMBLE),
        figures=((c.CLEAN_GUITAR, "comping"), (c.OVERDRIVEN_GUITAR, "power"), (c.PIANO, "comping"), (c.STEEL_GUITAR, "comping")),
        basses=(c.FINGER_BASS, c.PICKED_BASS),
        bass_patterns=("pulse", "half"),
        swells=(c.BRASS_SECTION, c.ROCK_ORGAN, c.DISTORTION_GUITAR),
        kits=(c.STANDARD_KIT, c.POWER_KIT),
        percussion="rock",
        timpani=False,
        volumes={"melody": 118, "melody_double": 92, "strings_pad": 58, "figure": 96, "bass": 96,
                 "brass": 70, "percussion": 80},
        reverb_scale=0.6,
    ),
    "electronic": Ensemble(
        leads=(c.SAW_LEAD, c.SQUARE_LEAD, c.CHARANG, c.SYNTH_BRASS),
        doubles=((c.SQUARE_LEAD, 1), (c.CRYSTAL, 1), (c.SAW_LEAD, -1), (c.ELECTRIC_PIANO_2, 0)),
        pads=(c.WARM_PAD, c.POLYSYNTH, c.CHOIR_PAD, c.SWEEP_PAD),
        figures=((c.SAW_LEAD, "arp16"), (c.CRYSTAL, "arp16"), (c.ELECTRIC_PIANO_2, "arpeggio"), (c.SQUARE_LEAD, "arp16")),
        basses=(c.SYNTH_BASS_1, c.SYNTH_BASS_2),
        bass_patterns=("pulse",),
        swells=(c.SYNTH_BRASS, c.SWEEP_PAD, c.POLYSYNTH),
        kits=(c.TR808_KIT, c.ELECTRONIC_KIT),
        percussion="electronic",
        timpani=False,
        volumes={"melody": 116, "melody_double": 92, "strings_pad": 66, "figure": 82, "bass": 96,
                 "brass": 64, "percussion": 84},
        reverb_scale=0.55,
    ),
    "chamber": Ensemble(
        leads=(c.FLUTE, c.CLARINET, c.VIOLIN, c.PIANO),
        doubles=((c.CELLO, -1), (c.VIOLA, 0), (c.CLARINET, 0), (c.VIOLIN, 1)),
        pads=(c.STRING_ENSEMBLE, c.SLOW_STRINGS, c.CHOIR),
        figures=((c.PIANO, "broken"), (c.NYLON_GUITAR, "arpeggio"), (c.HARP, "alberti"), (c.PIANO, "alberti")),
        basses=(c.CELLO, c.CONTRABASS),
        bass_patterns=("half", "whole"),
        swells=(c.FRENCH_HORN, c.CLARINET, c.VIOLA),
        kits=(c.BRUSH_KIT,),
        percussion="light",
        timpani=False,
        volumes={"melody": 110, "melody_double": 80, "strings_pad": 56, "figure": 100, "bass": 84,
                 "brass": 60, "percussion": 80},
        reverb_scale=0.9,
    ),
}

# Words a listener (or talk mode) may use that ask for an ensemble rather than just a style. Style
# names themselves ("cinematic", "classical"...) aren't here: they shape the music, not who plays it.
ENSEMBLE_WORDS: dict[str, str] = {
    "orchestra": "orchestra", "orchestral": "orchestra", "symphonic": "orchestra", "epic": "orchestra",
    "film": "orchestra", "movie": "orchestra", "symphony": "orchestra",
    "band": "band", "rock": "band", "punk": "band", "metal": "band", "funk": "band", "indie": "band",
    "electronic": "electronic", "digital": "electronic", "synth": "electronic", "edm": "electronic",
    "techno": "electronic", "house": "electronic", "dance": "electronic", "lofi": "electronic",
    "lo-fi": "electronic", "chiptune": "electronic", "ambient": "electronic", "trance": "electronic",
    "chamber": "chamber", "acoustic": "chamber", "unplugged": "chamber", "folk": "chamber",
    "string quartet": "chamber", "quartet": "chamber",
}


def ensemble_for_word(word: str | None) -> str | None:
    key = (word or "").strip().lower().replace("_", "-")
    return ENSEMBLE_WORDS.get(key) or ENSEMBLE_WORDS.get(key.replace("-", ""))


def choose(style: Style, ensemble: str | None = None, variation: int | None = None) -> tuple[str, Orchestration, float]:
    """(ensemble name, orchestration, reverb scale) for a song.

    No ensemble and no variation: the style's own orchestra, exactly as designed. Otherwise the
    named ensemble (or, with a variation but no name, one picked by it), with an instrument for each
    role picked by the variation (the first of each list when there's none).
    """
    if ensemble is None and variation is None:
        return "orchestra", style.orchestration, 1.0
    rng = random.Random(variation) if variation is not None else None
    name = ensemble or rng.choice(sorted(ENSEMBLES))
    if name not in ENSEMBLES:
        raise ValueError(f"Unknown ensemble {name!r}; choose one of {', '.join(sorted(ENSEMBLES))}.")
    band = ENSEMBLES[name]

    def pick(options):
        return rng.choice(options) if rng is not None else options[0]

    lead = pick(band.leads)
    double, double_octave = pick([d for d in band.doubles if d[0] != lead] or band.doubles)
    figure, pattern = pick(band.figures)
    orchestration = replace(
        style.orchestration,
        lead=lead,
        double=double,
        double_octave=double_octave,
        pad=pick(band.pads),
        figure=figure,
        figure_pattern=pattern,
        bass=pick(band.basses),
        bass_pattern=pick(band.bass_patterns),
        brass=pick([sw for sw in band.swells if sw not in (lead, double)] or band.swells),
        kit=pick(band.kits),
        percussion=band.percussion,
        timpani=band.timpani,
        volumes=dict(band.volumes),
    )
    return name, orchestration, band.reverb_scale
