"""Instruments by the names people use, as General MIDI programs (and drum kits).

The chat and the Studio offer these names; Gemini must pick one of them, so it can't ask for an
instrument the soundfont doesn't have.
"""

INSTRUMENTS: dict[str, int] = {
    "piano": 0, "bright piano": 1, "electric piano": 4, "rhodes": 4, "harpsichord": 6, "music box": 10,
    "vibraphone": 11, "marimba": 12, "xylophone": 13, "bells": 14, "organ": 16, "rock organ": 18,
    "church organ": 19, "accordion": 21, "harmonica": 22,
    "nylon guitar": 24, "acoustic guitar": 25, "jazz guitar": 26, "clean electric guitar": 27,
    "overdriven guitar": 29, "distortion guitar": 30,
    "upright bass": 32, "bass guitar": 33, "picked bass": 34, "fretless bass": 35, "slap bass": 36,
    "synth bass": 38,
    "violin": 40, "viola": 41, "cello": 42, "contrabass": 43, "pizzicato strings": 45, "harp": 46,
    "timpani": 47, "strings": 48, "slow strings": 49, "synth strings": 50, "choir": 52, "voice": 53,
    "trumpet": 56, "trombone": 57, "tuba": 58, "muted trumpet": 59, "french horn": 60, "brass": 61,
    "soprano sax": 64, "alto sax": 65, "tenor sax": 66, "baritone sax": 67, "oboe": 68, "english horn": 69,
    "bassoon": 70, "clarinet": 71, "piccolo": 72, "flute": 73, "recorder": 74, "pan flute": 75,
    "whistle": 78, "ocarina": 79,
    "square lead": 80, "saw lead": 81, "synth lead": 81, "warm pad": 89, "polysynth": 90, "choir pad": 91,
    "sitar": 104, "banjo": 105, "koto": 107, "kalimba": 108, "bagpipe": 109, "fiddle": 110,
    "steel drums": 114,
}

DRUM_KITS: dict[str, int] = {
    "standard kit": 0, "room kit": 8, "rock kit": 16, "electronic kit": 24, "808 kit": 25, "jazz kit": 32,
    "brush kit": 40, "orchestral percussion": 48,
}

BY_PROGRAM = {program: name for name, program in reversed(list(INSTRUMENTS.items()))}
KIT_BY_PROGRAM = {program: name for name, program in DRUM_KITS.items()}


def program_for(name: str, drums: bool) -> int | None:
    """The program a name means for a pitched track (drums=False) or the drum track; None if it
    isn't one this track can play."""
    return (DRUM_KITS if drums else INSTRUMENTS).get(name.strip().lower())


def instrument_name(program: int, drums: bool) -> str:
    if drums:
        return KIT_BY_PROGRAM.get(program, "drum kit")
    return BY_PROGRAM.get(program, f"instrument {program}")
