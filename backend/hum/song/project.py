"""The song as one editable project: the model the arranger writes, the renderer plays, the chat
commands change and the Studio page edits. It is plain data with a JSON form, so the app and the
server hold exactly the same thing.

Times are in beats from the start of the song (4 beats to a bar). `phrase` keeps the hum's tune as
arranged from (quantized, in the key, at its sung pitch), so the song can be arranged again in
another style without hearing the hum again.
"""

import copy
from dataclasses import asdict, dataclass, field

FORMAT_VERSION = 1
BEATS_PER_BAR = 4
ROLES = ("melody", "chords", "bass", "pad", "drums")
SECTION_NAMES = ("intro", "verse", "chorus", "outro")
MAX_INTENSITY = 2  # 0: barely there, 1: light, 2: full


@dataclass
class Note:
    pitch: int  # MIDI note number; for drums, the General MIDI drum sound
    start: float  # beats
    duration: float  # beats
    velocity: int = 90

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class Effects:
    """Per-track mixer settings. Neutral values do nothing."""

    reverb: float = 0.0  # 0 (dry) to 1 (far away)
    eq_low: float = 0.0  # dB, -12 to 12, below ~200 Hz
    eq_high: float = 0.0  # dB, -12 to 12, above ~5 kHz
    compression: float = 0.0  # 0 (none) to 1 (squashed)


@dataclass
class Track:
    id: str
    name: str
    role: str
    program: int  # General MIDI program; for drums, the drum kit
    notes: list[Note] = field(default_factory=list)
    volume: float = 0.8  # 0 to 1
    pan: float = 0.0  # -1 (left) to 1 (right)
    mute: bool = False
    solo: bool = False
    effects: Effects = field(default_factory=Effects)

    @property
    def is_drums(self) -> bool:
        return self.role == "drums"


@dataclass
class Section:
    name: str  # one of SECTION_NAMES
    start_bar: int
    bars: int
    intensity: int = 1
    variation: int = 0  # 0 is the arrangement as first made; each "play it differently" adds one

    @property
    def start(self) -> float:
        return self.start_bar * BEATS_PER_BAR

    @property
    def end(self) -> float:
        return (self.start_bar + self.bars) * BEATS_PER_BAR


@dataclass
class ChordSymbol:
    bar: int
    root: int  # pitch class, 0 = C
    quality: str  # see harmony.QUALITIES
    degree: str  # roman numeral in the key, e.g. "vi"


@dataclass
class Project:
    tempo: float
    tonic: str
    mode: str
    preset: str
    mood: str = "neutral"
    swing: float = 0.5  # where the off-beat eighth falls: 0.5 is straight, 0.66 a full shuffle
    transpose: int = 0  # semitones the whole song sits from the hum's own key
    hum_tempo: float = 0.0  # the tempo the hum was sung at; 0 when unknown
    # What the song was arranged with besides genre and mood, so it can be arranged again without
    # losing earlier edits: a tempo multiplier, each half's energy, the pad (None: the genre decides),
    # and the parts taken out.
    speed: float = 1.0
    energy: list[int] = field(default_factory=lambda: [0, 0])
    pad: bool | None = None
    removed: list[str] = field(default_factory=list)
    phrase: list[Note] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    chords: list[ChordSymbol] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)
    hum: str | None = None  # the upload this came from

    @property
    def bars(self) -> int:
        return max((s.start_bar + s.bars for s in self.sections), default=0)

    @property
    def length_beats(self) -> float:
        return self.bars * BEATS_PER_BAR

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.tempo

    @property
    def length_seconds(self) -> float:
        return self.length_beats * self.seconds_per_beat

    def track(self, track_id: str) -> Track:
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(track_id)

    def section(self, name: str) -> Section:
        for section in self.sections:
            if section.name == name:
                return section
        raise KeyError(name)

    def copy(self) -> "Project":
        return copy.deepcopy(self)

    def to_json(self) -> dict:
        return {"version": FORMAT_VERSION, **asdict(self)}

    @classmethod
    def from_json(cls, data: dict) -> "Project":
        """Reads a project sent by the app. Raises ValueError when it isn't one."""
        if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
            raise ValueError("That isn't a song project this server can read.")
        try:
            project = cls(
                tempo=_number(data["tempo"], 30, 300),
                tonic=str(data["tonic"]),
                mode=_one_of(data["mode"], ("major", "minor")),
                preset=str(data["preset"]),
                mood=str(data.get("mood", "neutral")),
                swing=_number(data.get("swing", 0.5), 0.5, 0.75),
                transpose=int(_number(data.get("transpose", 0), -24, 24)),
                hum_tempo=_number(data.get("hum_tempo", 0.0), 0, 300),
                speed=_number(data.get("speed", 1.0), 0.25, 4),
                energy=[int(_number(e, -MAX_INTENSITY, MAX_INTENSITY)) for e in data.get("energy", [0, 0])][:2],
                pad=None if data.get("pad") is None else bool(data["pad"]),
                removed=[_one_of(r, ROLES) for r in data.get("removed", [])],
                phrase=[_note(n) for n in data.get("phrase", [])],
                sections=[_section(s) for s in data.get("sections", [])],
                chords=[ChordSymbol(int(c["bar"]), int(c["root"]) % 12, str(c["quality"]), str(c["degree"]))
                        for c in data.get("chords", [])],
                tracks=[_track(t) for t in data.get("tracks", [])],
                hum=data.get("hum"),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"That song project is missing something ({exc}).") from exc
        if len({t.id for t in project.tracks}) != len(project.tracks):
            raise ValueError("Two tracks in that project have the same id.")
        return project


def _number(value, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{value!r} isn't a number")
    if not low <= value <= high:
        raise ValueError(f"{value} isn't between {low} and {high}")
    return float(value)


def _one_of(value, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"{value!r} must be one of {', '.join(allowed)}")
    return value


def _note(data: dict) -> Note:
    return Note(
        pitch=int(_number(data["pitch"], 0, 127)),
        start=_number(data["start"], 0, 100_000),
        duration=_number(data["duration"], 1e-3, 100_000),
        velocity=int(_number(data.get("velocity", 90), 1, 127)),
    )


def _section(data: dict) -> Section:
    return Section(
        name=_one_of(data["name"], SECTION_NAMES),
        start_bar=int(_number(data["start_bar"], 0, 10_000)),
        bars=int(_number(data["bars"], 1, 10_000)),
        intensity=int(_number(data.get("intensity", 1), 0, MAX_INTENSITY)),
        variation=int(_number(data.get("variation", 0), 0, 1000)),
    )


def _track(data: dict) -> Track:
    fx = data.get("effects") or {}
    return Track(
        id=str(data["id"]),
        name=str(data.get("name", data["id"])),
        role=_one_of(data["role"], ROLES),
        program=int(_number(data["program"], 0, 127)),
        notes=[_note(n) for n in data.get("notes", [])],
        volume=_number(data.get("volume", 0.8), 0, 1),
        pan=_number(data.get("pan", 0.0), -1, 1),
        mute=bool(data.get("mute", False)),
        solo=bool(data.get("solo", False)),
        effects=Effects(
            reverb=_number(fx.get("reverb", 0.0), 0, 1),
            eq_low=_number(fx.get("eq_low", 0.0), -12, 12),
            eq_high=_number(fx.get("eq_high", 0.0), -12, 12),
            compression=_number(fx.get("compression", 0.0), 0, 1),
        ),
    )
