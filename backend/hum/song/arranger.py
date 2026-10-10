"""A hum's tune -> a whole song: intro, verse, chorus, outro, played by the genre's band.

Built on the quantized copy of the hum (in the key, on the beat grid); the raw transcription is
never touched. The tune is lifted by whole octaves into a lead register when it was hummed low,
and every other part is voiced underneath it, so the melody is always on top: highest in pitch,
and loudest in the mix (see ROLE_VOLUME).

Verse and chorus both carry the hum's phrase (repeated to at least four bars); the chorus is the
fuller one. The intro plays the opening chords, the outro cadences home.
"""

import math
from dataclasses import dataclass

import pretty_midi

from hum.transcription import NOTE_NAMES, SCALES, Transcription, tonic_pitch_class

from . import drums
from .harmony import DOMINANT, SUBDOMINANT, TONIC, Chord, chord_by_degree, colored, progression
from .parts import CHORD_FLOOR, bass_bar, chord_bar, pad_bar, voice
from .presets import DEFAULT_MOOD, DEFAULT_PRESET, Mood, Preset, feel_tempo, mood_for, preset_for
from .project import BEATS_PER_BAR, MAX_INTENSITY, Effects, Note, Project, Section, Track

MELODY_FLOOR = 60  # a hum lower than middle C is played an octave (or two) up
MIN_SECTION_BARS = 4
OUTRO_BARS = 2
CHORUS_LIFT = 8  # the tune is sung out a little more in the chorus
MELODY_MIN_VELOCITY = 75  # a soft hum still leads the song
DEFAULT_PAD = 89  # warm pad, for a mood that wants one in a genre that has none
ROLE_VOLUME = {"melody": 1.0, "chords": 0.55, "bass": 0.62, "pad": 0.36, "drums": 0.6}
ROLE_PAN = {"melody": 0.0, "chords": -0.2, "bass": 0.0, "pad": 0.25, "drums": 0.0}
ROLE_LABEL = {"melody": "Melody", "chords": "Chords", "bass": "Bass", "pad": "Pad", "drums": "Drums"}
# A section played differently an odd number of times also changes rhythm: these replace the genre's.
ALT_COMPING = {"hold": "pulse", "pulse": "arp", "lofi": "charleston", "power8": "power_hold", "power_hold": "power8",
               "stab": "pulse", "charleston": "lofi", "strum": "arp", "arp": "pulse"}
ALT_BASS = {"hold": "root_fifth", "root_fifth": "lofi", "eighths": "root_fifth", "lofi": "root_fifth",
            "offbeat": "eighths", "walking": "root_fifth"}


@dataclass(frozen=True)
class ArrangeOptions:
    preset: str = DEFAULT_PRESET
    mood: str = DEFAULT_MOOD
    speed: float = 1.0  # tempo multiplier on top of the genre's feel
    transpose: int = 0  # semitones
    energy: tuple[int, int] = (0, 0)  # added to the verse's and the chorus's intensity
    pad: bool | None = None  # None: the genre (and mood) decide
    removed: tuple[str, ...] = ()  # parts left out (never the melody)
    variations: tuple[tuple[str, int], ...] = ()  # (section, how many times it was asked to be played differently)


def phrase_of(transcription: Transcription) -> list[Note]:
    return [Note(n.pitch, n.start, n.duration, n.velocity) for n in transcription.quantized()]


def arrange(transcription: Transcription, options: ArrangeOptions = ArrangeOptions(), hum: str | None = None) -> Project:
    return arrange_phrase(phrase_of(transcription), transcription.tempo_bpm, transcription.tonic, transcription.mode,
                          options, hum)


def arrange_phrase(phrase: list[Note], hum_tempo: float, tonic: str, mode: str,
                   options: ArrangeOptions = ArrangeOptions(), hum: str | None = None) -> Project:
    if not phrase:
        raise ValueError("There's no tune to arrange.")
    preset, mood = preset_for(options.preset), mood_for(options.mood)
    tempo, beat_scale = feel_tempo(hum_tempo, preset, mood, options.speed)
    tonic_pc = (tonic_pitch_class(tonic) + options.transpose) % 12
    tune = _lifted([Note(n.pitch + options.transpose, n.start * beat_scale, n.duration * beat_scale, n.velocity)
                    for n in phrase])

    phrase_bars = max(1, math.ceil(max(n.end for n in tune) / BEATS_PER_BAR - 1e-6))
    repeats = math.ceil(MIN_SECTION_BARS / phrase_bars)
    variations = dict(options.variations)
    sections = _sections(preset, mood, options.energy, phrase_bars * repeats, variations)
    by_section = {}
    for section in sections:
        plain = progression(tune, phrase_bars, tonic_pc, mode, preset, mood)
        for _ in range(section.variation):  # each variation moves away from the one before
            plain = progression(tune, phrase_bars, tonic_pc, mode, preset, mood, avoid=plain)
        by_section[section.name] = [colored(c, preset) for c in plain]
    chords = _chords_by_bar(sections, by_section, tonic_pc, mode, preset, mood)

    scale = frozenset((tonic_pc + step) % 12 for step in SCALES[mode])
    builder = _Band(preset, mood, ceiling=min(n.pitch for n in tune) - 1, scale=scale, pad=options.pad)
    for section in sections:
        for bar in range(section.start_bar, section.start_bar + section.bars):
            builder.play_bar(section, bar, chords[bar], chords[bar + 1] if bar + 1 < len(chords) else None,
                             last_bar=bar == sections[-1].start_bar + sections[-1].bars - 1,
                             before_bigger=_before_bigger(sections, section, bar))
        if section.name in ("verse", "chorus"):
            lift = CHORUS_LIFT if section.name == "chorus" else 0
            for k in range(repeats):
                offset = section.start + k * phrase_bars * BEATS_PER_BAR
                builder.melody += [Note(n.pitch, n.start + offset, n.duration,
                                        _vel(max(n.velocity, MELODY_MIN_VELOCITY) + lift + mood.velocity_shift))
                                   for n in tune]

    return Project(
        tempo=tempo, tonic=NOTE_NAMES[tonic_pc], mode=mode, preset=preset.id, mood=mood.id, swing=preset.swing,
        transpose=options.transpose, hum_tempo=hum_tempo, phrase=list(phrase), sections=sections,
        chords=[chord.symbol(bar) for bar, chord in enumerate(chords)],
        tracks=[t for t in builder.tracks() if t.role == "melody" or t.role not in options.removed], hum=hum,
        speed=options.speed, energy=list(options.energy), pad=options.pad,
        removed=[r for r in options.removed if r != "melody"],
    )


def _lifted(tune: list[Note]) -> list[Note]:
    low = min(n.pitch for n in tune)
    octaves = max(0, math.ceil((MELODY_FLOOR - low) / 12))
    return [Note(n.pitch + 12 * octaves, n.start, n.duration, n.velocity) for n in tune]


def _sections(preset: Preset, mood: Mood, energy: tuple[int, int], body_bars: int, variations: dict) -> list[Section]:
    def level(base: int, extra: int) -> int:
        return max(0, min(MAX_INTENSITY, base + mood.intensity_shift + extra))

    plan = [
        ("intro", preset.intro_bars, preset.intro_intensity),
        ("verse", body_bars, level(1, energy[0])),
        ("chorus", body_bars, level(2, energy[1])),
        ("outro", OUTRO_BARS, 1),
    ]
    sections, bar = [], 0
    for name, bars, intensity in plan:
        sections.append(Section(name, bar, bars, intensity, variations.get(name, 0)))
        bar += bars
    return sections


def _chords_by_bar(sections, by_section, tonic_pc, mode, preset, mood) -> list[Chord]:
    def key_chord(degree: str) -> Chord:
        return colored(chord_by_degree(tonic_pc, mode, degree), preset)

    cadence = SUBDOMINANT[mode] if mood.chord_lean == "minor" else DOMINANT
    chords = []
    for section in sections:
        if section.name == "outro":
            chords += [key_chord(cadence)] * (section.bars - 1) + [key_chord(TONIC[mode])]
        else:
            phrase_chords = by_section[section.name]
            chords += [phrase_chords[i % len(phrase_chords)] for i in range(section.bars)]
    return chords


def _before_bigger(sections: list[Section], section: Section, bar: int) -> bool:
    """The section's last bar, when the next section is fuller: the drums fill into it."""
    following = sections.index(section) + 1
    return (bar == section.start_bar + section.bars - 1 and following < len(sections)
            and sections[following].intensity > section.intensity and section.intensity > 0)


class _Band:
    """Collects each part's notes, bar by bar."""

    def __init__(self, preset: Preset, mood: Mood, ceiling: int, scale: frozenset[int], pad: bool | None = None):
        self.preset, self.mood = preset, mood
        self.scale = scale
        self.ceiling = ceiling
        self.floor = min(CHORD_FLOOR, ceiling - 12)
        wants_pad = (preset.palette.pad is not None or mood.pad) if pad is None else pad
        self.pad_program = (preset.palette.pad if preset.palette.pad is not None else DEFAULT_PAD) if wants_pad else None
        self.melody, self.chords, self.bass, self.pad, self.drums = [], [], [], [], []
        self._voicing = None

    def play_bar(self, section: Section, bar: int, chord: Chord, following: Chord | None, *, last_bar: bool,
                 before_bigger: bool):
        preset, shift = self.preset, self.mood.velocity_shift
        intensity = section.intensity
        full = intensity >= 2
        self._voicing = voice(chord, self.floor, self.ceiling, self._voicing)
        varied = section.variation % 2 == 1
        comping = "hold" if last_bar else preset.comping if full else preset.comping_light
        comping = ALT_COMPING.get(comping, comping) if varied and not last_bar else comping
        self.chords += chord_bar(self._voicing, comping, bar, _vel(68 + 8 * intensity + shift))

        if section.name != "intro" or intensity > 0:
            line = "hold" if last_bar else preset.bass if full else preset.bass_light
            line = ALT_BASS.get(line, line) if varied and not last_bar else line
            self.bass += bass_bar(chord, following, line, bar, _vel(84 + 6 * intensity + shift), self.scale)

        if self.pad_program is not None and section.name != "verse":
            self.pad += pad_bar(chord, self.ceiling, bar, _vel(56 + shift))

        if last_bar:
            self.drums += drums.end_hit(bar, shift)
        else:
            crash = section.name == "chorus" and bar == section.start_bar and full
            self.drums += drums.drum_bar(preset.groove, intensity, bar, crash=crash, fill=before_bigger,
                                         velocity_shift=shift)

    def tracks(self) -> list[Track]:
        palette, mood = self.preset.palette, self.mood
        wet = min(1.0, self.preset.reverb + mood.reverb_add)
        plan = [
            ("melody", palette.melody, self.melody, Effects(reverb=wet, eq_high=mood.brightness_db, compression=0.2)),
            ("chords", palette.chords, self.chords, Effects(reverb=wet, eq_high=mood.brightness_db, compression=0.1)),
            ("bass", palette.bass, self.bass, Effects(reverb=0.05, compression=0.4)),
            ("pad", self.pad_program, self.pad, Effects(reverb=min(1.0, wet + 0.15), eq_high=mood.brightness_db - 2)),
            ("drums", palette.drums, self.drums, Effects(reverb=wet / 2, eq_high=mood.brightness_db, compression=0.35)),
        ]
        return [
            Track(id=role, name=track_name(role, program), role=role, program=program,
                  notes=sorted(notes, key=lambda n: (n.start, n.pitch)), volume=ROLE_VOLUME[role], pan=ROLE_PAN[role],
                  effects=effects)
            for role, program, notes, effects in plan
            if program is not None and notes
        ]


def track_name(role: str, program: int) -> str:
    if role == "drums":
        return ROLE_LABEL[role]
    return f"{ROLE_LABEL[role]} · {pretty_midi.program_to_instrument_name(program)}"


def _vel(value: float) -> int:
    return max(1, min(127, round(value)))
