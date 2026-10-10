"""Applies edits to a song project. Pure: a project and edits in, a new project and what changed out.

Mixer edits (volume, mute, solo, effects) only touch track settings, so nothing has to be rendered
again. Edits that change the notes (genre, mood, a part, a section, energy) arrange the song again
from the hum's phrase with everything else the project remembers (hum/song/arranger.py), then carry
over what the listener changed by hand: instruments, volumes, pans, mutes. `changed` names the
tracks whose sound changed, which are the only ones the renderer has to make again.
"""

from dataclasses import dataclass, field, replace

from hum.song.arranger import ArrangeOptions, arrange_phrase, track_name
from hum.song.instruments import program_for
from hum.song.presets import MOODS, PRESETS, feel_tempo, mood_for, preset_for
from hum.song.project import MAX_INTENSITY, ROLES, Project, Track
from hum.song.render import stem_key
from hum.transcription import NOTE_NAMES, tonic_pitch_class

from .commands import Edit

TEMPO_RANGE = (40.0, 220.0)
TEMPO_STEP = {"slight": 0.05, "moderate": 0.1, "strong": 0.2}
VOLUME_STEP = {"slight": 0.1, "moderate": 0.2, "strong": 0.35}
EFFECT_STEP = {"slight": 0.15, "moderate": 0.3, "strong": 0.5}  # reverb, compression: share of their range
EQ_STEP = {"slight": 2.0, "moderate": 4.0, "strong": 7.0}  # dB
MAX_TRANSPOSE = 12
MELODY_GAP = 0.05  # no other part is turned up past the melody, less this
TEMPO_ROUNDING = 0.25  # bpm: a re-arranged tempo this close to the old one is the old one


class EditRefused(ValueError):
    """An edit that can't be done to this song; the message says why, kindly."""


@dataclass
class Result:
    project: Project
    changed: list[str] = field(default_factory=list)  # tracks whose sound changed (render again)
    mixed: list[str] = field(default_factory=list)  # tracks whose mixer settings changed only
    done: list[str] = field(default_factory=list)  # short labels for what was done, e.g. "drums quieter"
    refused: list[str] = field(default_factory=list)  # why an edit wasn't done

    @property
    def label(self) -> str:
        return ", ".join(self.done)


def apply(project: Project, edits: list[Edit]) -> Result:
    """Each edit in order; one that can't be done is skipped with its reason, the others still apply."""
    current = project.copy()
    done, refused = [], []
    for edit in edits:
        try:
            current, label = _apply_one(current, edit)
            done.append(label)
        except EditRefused as exc:
            refused.append(str(exc))
    changed, mixed = _differences(project, current)
    return Result(current, changed, mixed, done, refused)


def _apply_one(p: Project, e: Edit) -> tuple[Project, str]:
    a = e.action
    if a in ("set_tempo", "change_tempo"):
        return _tempo(p, e)
    if a in ("transpose", "set_key"):
        return _transpose(p, e)
    if a == "set_genre":
        genre = _need(e.genre, "Which genre?")
        if genre == p.preset:
            raise EditRefused(f"It's already {PRESETS[genre].label.lower()}.")
        # a new genre is a new band: only the listener's tempo, key, energy and parts carry over
        return _arranged(p, preset=genre), f"{PRESETS[genre].label.lower()} now"
    if a == "set_mood":
        mood = _need(e.mood, "Which mood?")
        if mood == p.mood:
            raise EditRefused(f"It's already {MOODS[mood].label.lower()}.")
        return _carried(p, _arranged(p, mood=mood)), f"{MOODS[mood].label.lower()} mood"
    if a == "set_instrument":
        return _instrument(p, e)
    if a in ("change_volume", "mute", "unmute", "solo", "unsolo"):
        return _mixer(p, e)
    if a == "change_effect":
        return _effect(p, e)
    if a == "add_part":
        return _add_part(p, _need(e.part, "Which part should I add?"))
    if a == "remove_part":
        return _remove_part(p, _need(e.part, "Which part should I take out?"))
    if a == "regenerate_section":
        name = _need(e.section, "Which part of the song should I play differently?")
        variations = {s.name: s.variation for s in p.sections}
        variations[name] = variations.get(name, 0) + 1
        return _carried(p, _arranged(p, variations=tuple(variations.items()))), f"a new take on the {name}"
    if a == "change_energy":
        return _energy(p, e)
    raise EditRefused("I can't do that one yet.")


# ── Tempo and key ──────────────────────────────────────────────────────


def _tempo(p: Project, e: Edit) -> tuple[Project, str]:
    if e.action == "set_tempo":
        target = _need(e.value, "What tempo would you like?")
    else:
        step = TEMPO_STEP[e.amount or "moderate"]
        target = p.tempo * (1 + step if _need(e.direction, "Faster or slower?") == "up" else 1 - step)
    tempo = round(min(max(target, TEMPO_RANGE[0]), TEMPO_RANGE[1]), 1)
    if tempo == p.tempo:
        raise EditRefused(f"It's already as {'fast' if tempo >= TEMPO_RANGE[1] else 'slow'} as I can play it.")
    base, _ = feel_tempo(p.hum_tempo or p.tempo, preset_for(p.preset), mood_for(p.mood))
    updated = replace(p, tempo=tempo, speed=round(tempo / base, 4))
    return updated, f"{round(tempo)} bpm"


def _transpose(p: Project, e: Edit) -> tuple[Project, str]:
    tonic = tonic_pitch_class(p.tonic)
    if e.action == "set_key":
        target = tonic_pitch_class(_need(e.key, "Which key?"))
        shift = (target - tonic + 6) % 12 - 6  # the nearer way: at most a tritone
    else:
        shift = round(_need(e.value, "How many semitones?"))
    if shift == 0:
        raise EditRefused(f"It's already in {p.tonic} {p.mode}.")
    total = p.transpose + shift
    if abs(total) > MAX_TRANSPOSE:
        raise EditRefused("That's as far from your hum's key as I'll take it: an octave either way.")
    tracks = []
    for track in p.tracks:
        if track.role != "drums":
            pitches = [n.pitch + shift for n in track.notes]
            if pitches and (min(pitches) < 0 or max(pitches) > 127):
                raise EditRefused("That would take the notes out of range.")
            track = replace(track, notes=[replace(n, pitch=n.pitch + shift) for n in track.notes])
        tracks.append(track)
    key = NOTE_NAMES[(tonic + shift) % 12]
    chords = [replace(c, root=(c.root + shift) % 12) for c in p.chords]
    return replace(p, tonic=key, transpose=total, tracks=tracks, chords=chords), f"in {key} {p.mode}"


# ── Instruments and the mixer ──────────────────────────────────────────


def _instrument(p: Project, e: Edit) -> tuple[Project, str]:
    track = _track(p, _need(e.part, "Which part should change instrument?"))
    name = _need(e.instrument, "Which instrument?")
    program = program_for(name, track.is_drums)
    if program is None:
        kind = "a drum kit" if track.is_drums else "an instrument that plays notes"
        raise EditRefused(f"The {track.role} part needs {kind}, so {name} won't work there.")
    if program == track.program:
        raise EditRefused(f"The {track.role} is already {name}.")
    return _with_track(p, replace(track, program=program, name=track_name(track.role, program))), f"{track.role} on {name}"


def _mixer(p: Project, e: Edit) -> tuple[Project, str]:
    a = e.action
    if a == "unsolo" and e.part is None:
        return replace(p, tracks=[replace(t, solo=False) for t in p.tracks]), "everyone back in"
    track = _track(p, _need(e.part, "Which part?"))
    if a == "mute":
        return _with_track(p, replace(track, mute=True)), f"{track.role} muted"
    if a == "unmute":
        return _with_track(p, replace(track, mute=False)), f"{track.role} back in"
    if a == "solo":
        return replace(p, tracks=[replace(t, solo=t.id == track.id) for t in p.tracks]), f"just the {track.role}"
    if a == "unsolo":
        return _with_track(p, replace(track, solo=False)), f"{track.role} unsoloed"
    up = _need(e.direction, "Louder or quieter?") == "up"
    step = VOLUME_STEP[e.amount or "moderate"]
    volume = round(min(1.0, max(0.0, track.volume + (step if up else -step))), 2)
    melody = next((t for t in p.tracks if t.role == "melody"), None)
    if track.role != "melody" and melody and volume > melody.volume - MELODY_GAP:
        volume = round(max(track.volume, melody.volume - MELODY_GAP), 2)
        if volume == track.volume:
            raise EditRefused(f"The {track.role} can't go above the melody, or your tune would get lost.")
    if volume == track.volume:
        raise EditRefused(f"The {track.role} is already as {'loud' if up else 'quiet'} as it goes.")
    updated = _with_track(p, replace(track, volume=volume))
    if track.role == "melody" and not up:  # keep everyone under the tune
        updated = replace(updated, tracks=[
            replace(t, volume=min(t.volume, round(volume - MELODY_GAP, 2))) if t.role != "melody" else t
            for t in updated.tracks
        ])
    return updated, f"{track.role} {'louder' if up else 'quieter'}"


def _effect(p: Project, e: Edit) -> tuple[Project, str]:
    effect = _need(e.effect, "Which effect?")
    up = _need(e.direction, "More or less?") == "up"
    amount = e.amount or "moderate"
    targets = [_track(p, e.part)] if e.part else p.tracks
    tracks = {t.id: t for t in p.tracks}
    for track in targets:
        fx = track.effects
        if effect in ("reverb", "compression"):
            step = EFFECT_STEP[amount] * (1 if up else -1)
            fx = replace(fx, **{effect: round(min(1.0, max(0.0, getattr(fx, effect) + step)), 2)})
        else:
            attr = "eq_high" if effect == "brightness" else "eq_low"
            step = EQ_STEP[amount] * (1 if up else -1)
            fx = replace(fx, **{attr: round(min(12.0, max(-12.0, getattr(fx, attr) + step)), 1)})
        tracks[track.id] = replace(track, effects=fx)
    words = {"reverb": ("more", "less"), "compression": ("more", "less"), "brightness": ("brighter", "darker"),
             "bass_boost": ("more low end", "less low end")}
    word = words[effect][0 if up else 1]
    label = f"{word} {effect}" if effect in ("reverb", "compression") else word
    where = f" on the {e.part}" if e.part else ""
    return replace(p, tracks=list(tracks.values())), label + where


# ── Parts, sections, energy (arranged again) ───────────────────────────


def _add_part(p: Project, role: str) -> tuple[Project, str]:
    if any(t.role == role for t in p.tracks):
        raise EditRefused(f"There's already a {role}.")
    removed = tuple(r for r in p.removed if r != role)
    fresh = _arranged(p, removed=removed, pad=True if role == "pad" else p.pad)
    new = next((t for t in fresh.tracks if t.role == role), None)
    if new is None:
        raise EditRefused(f"I couldn't write a {role} part for this song.")
    order = {r: i for i, r in enumerate(ROLES)}
    tracks = sorted([*p.tracks, new], key=lambda t: order[t.role])
    return replace(p, tracks=tracks, removed=list(removed), pad=fresh.pad), f"{role} added"


def _remove_part(p: Project, role: str) -> tuple[Project, str]:
    if role == "melody":
        raise EditRefused("The melody is your hum, so it stays. I can make it quieter if you like.")
    if not any(t.role == role for t in p.tracks):
        raise EditRefused(f"There's no {role} to take out.")
    tracks = [t for t in p.tracks if t.role != role]
    return replace(p, tracks=tracks, removed=sorted({*p.removed, role}), pad=False if role == "pad" else p.pad), f"{role} out"


def _energy(p: Project, e: Edit) -> tuple[Project, str]:
    section = _need(e.section, "Which part: the verse or the chorus?")
    if section not in ("verse", "chorus"):
        raise EditRefused("I can make the verse or the chorus bigger or calmer.")
    index = 0 if section == "verse" else 1
    up = _need(e.direction, "Bigger or calmer?") == "up"
    energy = list(p.energy)
    energy[index] = max(-MAX_INTENSITY, min(MAX_INTENSITY, energy[index] + (1 if up else -1)))
    before = p.section(section).intensity
    fresh = _carried(p, _arranged(p, energy=tuple(energy)))
    if fresh.section(section).intensity == before:
        raise EditRefused(f"The {section} is already as {'big' if up else 'calm'} as it gets.")
    return fresh, f"{'bigger' if up else 'calmer'} {section}"


def _arranged(p: Project, **changes) -> Project:
    """The song arranged again with what the project remembers, and `changes`."""
    options = ArrangeOptions(
        preset=p.preset, mood=p.mood, speed=p.speed, transpose=p.transpose, energy=tuple(p.energy), pad=p.pad,
        removed=tuple(p.removed), variations=tuple((s.name, s.variation) for s in p.sections if s.variation),
    )
    options = replace(options, **changes)
    hum_tonic = NOTE_NAMES[(tonic_pitch_class(p.tonic) - p.transpose) % 12]
    return arrange_phrase(p.phrase, p.hum_tempo or p.tempo, hum_tonic, p.mode, options, hum=p.hum)


def _carried(old: Project, fresh: Project) -> Project:
    """`fresh` with the listener's own choices from `old` kept, part by part: the instrument and the
    mixer settings (effects come with the arrangement)."""
    before = {t.role: t for t in old.tracks}
    tracks = []
    for track in fresh.tracks:
        was = before.get(track.role)
        if was is not None:
            track = replace(track, program=was.program, name=was.name, volume=was.volume, pan=was.pan,
                            mute=was.mute, solo=was.solo)
        tracks.append(track)
    # the same tempo up to rounding stays exactly the same, so unchanged parts aren't rendered again
    tempo = old.tempo if abs(fresh.tempo - old.tempo) < TEMPO_ROUNDING else fresh.tempo
    return replace(fresh, tracks=tracks, tempo=tempo)


# ── Helpers ────────────────────────────────────────────────────────────


def _need(value, question: str):
    if value is None:
        raise EditRefused(question)
    return value


def _track(p: Project, role: str) -> Track:
    for track in p.tracks:
        if track.role == role:
            return track
    raise EditRefused(f"There's no {role} in the song right now. Want me to add one?")


def _with_track(p: Project, track: Track) -> Project:
    return replace(p, tracks=[track if t.id == track.id else t for t in p.tracks])


def _differences(before: Project, after: Project) -> tuple[list[str], list[str]]:
    old = {t.id: t for t in before.tracks}
    changed, mixed = [], []
    for track in after.tracks:
        was = old.get(track.id)
        if was is None or stem_key(before, was) != stem_key(after, track):
            changed.append(track.id)
        elif (was.volume, was.pan, was.mute, was.solo, was.effects) != (track.volume, track.pan, track.mute, track.solo, track.effects):
            mixed.append(track.id)
    removed = [t for t in old if t not in {t.id for t in after.tracks}]
    return changed, mixed + removed
