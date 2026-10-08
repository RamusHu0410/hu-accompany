"""A project -> sound, and -> a MIDI file.

Each track is rendered on its own (a "stem", by FluidSynth) and kept on disk under a name made from
everything that changes its sound: the notes, the instrument, the tempo and the swing. Rendering a
project again only renders the stems that changed; volume, pan, mute, solo and effects are mixer
settings, applied afterwards, so changing them renders nothing.

Every stem is brought to the same loudness before its volume is applied, so a track's volume means
the same thing whatever the instrument: the melody (volume 1) is always the loudest part.
"""

import hashlib
import io
import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from hum.engine.accompanist.audio.render import find_soundfont, render_midi
from hum.rawplay import PEAK, RenderUnavailable, without_trailing_silence

from .project import Project, Track

try:
    from pedalboard import Compressor, Gain, HighShelfFilter, Limiter, LowShelfFilter, Pedalboard, Reverb
except Exception:  # noqa: BLE001 - a missing native library raises OSError, not ImportError
    Pedalboard = None

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
STEM_VERSION = 1  # bump when the way stems are made changes, so old ones aren't reused
STEM_RMS = 0.1  # -20 dBFS: every stem's loudness while it plays, before its volume
TAIL_SECONDS = 2.5  # room for the last chord and the reverb to ring out
MAX_STEMS_KEPT = 400
WORKERS = 4


@dataclass
class Mix:
    wav: bytes
    rendered: list[str] = field(default_factory=list)  # tracks whose stems had to be made
    reused: list[str] = field(default_factory=list)  # tracks whose stems were already there
    levels: dict[str, float] = field(default_factory=dict)  # each audible track's loudness in the mix, dBFS


def swung(beat: float, swing: float) -> float:
    """Where a beat position lands once off-beat eighths are pushed late (0.5 is straight)."""
    whole, part = divmod(beat, 1.0)
    if part < 0.5:
        return whole + part * (swing / 0.5)
    return whole + swing + (part - 0.5) * ((1 - swing) / 0.5)


def track_midi(project: Project, track: Track) -> pretty_midi.PrettyMIDI:
    midi = pretty_midi.PrettyMIDI(initial_tempo=project.tempo)
    midi.instruments.append(_instrument(project, track))
    return midi


def project_midi(project: Project) -> pretty_midi.PrettyMIDI:
    """Every track, muted or not, on its own MIDI track (drums on channel 10)."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=project.tempo)
    midi.instruments.extend(_instrument(project, track) for track in project.tracks)
    return midi


def export_midi(project: Project) -> bytes:
    buffer = io.BytesIO()
    project_midi(project).write(buffer)
    return buffer.getvalue()


def _instrument(project: Project, track: Track) -> pretty_midi.Instrument:
    spb = project.seconds_per_beat
    instrument = pretty_midi.Instrument(program=track.program, is_drum=track.is_drums, name=track.name)
    for note in track.notes:
        start = swung(note.start, project.swing) * spb
        end = max(swung(note.end, project.swing) * spb, start + 0.02)
        instrument.notes.append(pretty_midi.Note(velocity=note.velocity, pitch=note.pitch, start=start, end=end))
    return instrument


def stem_key(project: Project, track: Track) -> str:
    identity = {
        "version": STEM_VERSION, "program": track.program, "drums": track.is_drums, "tempo": project.tempo,
        "swing": project.swing, "notes": [(n.pitch, n.start, n.duration, n.velocity) for n in track.notes],
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]


def mix(project: Project, stem_dir: Path) -> Mix:
    """The project as a 16-bit stereo WAV. Raises RenderUnavailable without FluidSynth or a soundfont."""
    try:
        soundfont = find_soundfont()
    except FileNotFoundError as exc:
        raise RenderUnavailable(str(exc)) from exc
    stem_dir.mkdir(parents=True, exist_ok=True)
    soloed = [t for t in project.tracks if t.solo]
    audible = [t for t in (soloed or project.tracks) if not t.mute and t.notes]
    paths = {t.id: stem_dir / f"{stem_key(project, t)}.wav" for t in audible}
    missing = [t for t in audible if not paths[t.id].is_file()]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(lambda t: _render_stem(project, t, paths[t.id], soundfont), missing))

    length = int((project.length_seconds + TAIL_SECONDS) * SAMPLE_RATE)
    bus = np.zeros((length, 2), dtype=np.float32)
    levels = {}
    for track in audible:
        stem, _ = sf.read(paths[track.id], dtype="float32", always_2d=True)
        os.utime(paths[track.id])  # recently used: kept when old stems are cleared out
        part = _processed(_fit(stem, length), track)
        levels[track.id] = _db(_active_rms(part))
        bus += part
    _forget_old_stems(stem_dir)
    out = _mastered(bus)
    buffer = io.BytesIO()
    sf.write(buffer, out, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    rendered = [t.id for t in missing]
    return Mix(buffer.getvalue(), rendered=rendered, reused=[t.id for t in audible if t.id not in rendered],
               levels=levels)


def _render_stem(project: Project, track: Track, path: Path, soundfont: str) -> None:
    midi = track_midi(project, track)
    # a silent control change at the very end keeps every stem the length of the song
    midi.instruments[0].control_changes.append(
        pretty_midi.ControlChange(number=7, value=100, time=project.length_seconds + TAIL_SECONDS))
    with tempfile.TemporaryDirectory(prefix="hum-stem-") as scratch:
        midi_path, wav_path = os.path.join(scratch, "stem.mid"), os.path.join(scratch, "stem.wav")
        midi.write(midi_path)
        try:
            render_midi(midi_path, wav_path, soundfont=soundfont, sample_rate=SAMPLE_RATE)
        except (FileNotFoundError, RuntimeError) as exc:
            raise RenderUnavailable(str(exc)) from exc
        samples, _ = sf.read(wav_path, dtype="float32", always_2d=True)
    level = _active_rms(samples)
    if level > 0:
        samples = samples * (STEM_RMS / level)
    partial = path.with_suffix(".partial.wav")
    sf.write(partial, samples, SAMPLE_RATE, subtype="FLOAT")
    os.replace(partial, path)  # never leave a half-written stem where a later mix would trust it


def _fit(samples: np.ndarray, length: int) -> np.ndarray:
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    if len(samples) >= length:
        return samples[:length]
    return np.pad(samples, ((0, length - len(samples)), (0, 0)))


def _processed(stem: np.ndarray, track: Track) -> np.ndarray:
    audio = stem
    board = _board(track)
    if board is not None:
        audio = board(np.ascontiguousarray(stem.T), SAMPLE_RATE).T
    angle = (track.pan + 1) * np.pi / 4  # equal-power pan, unity in the middle
    gains = np.array([np.cos(angle), np.sin(angle)], dtype=np.float32) * np.sqrt(2)
    return (audio * gains * track.volume).astype(np.float32)


def _board(track: Track):
    fx = track.effects
    if Pedalboard is None:
        return None
    plugins = []
    if fx.eq_low:
        plugins.append(LowShelfFilter(cutoff_frequency_hz=200, gain_db=fx.eq_low))
    if fx.eq_high:
        plugins.append(HighShelfFilter(cutoff_frequency_hz=5000, gain_db=fx.eq_high))
    if fx.compression:
        plugins.append(Compressor(threshold_db=-14 - 16 * fx.compression, ratio=1 + 5 * fx.compression,
                                  attack_ms=8, release_ms=150))
        plugins.append(Gain(gain_db=4 * fx.compression))  # make up roughly what was taken
    if fx.reverb:
        plugins.append(Reverb(room_size=0.3 + 0.55 * fx.reverb, damping=0.5, wet_level=0.4 * fx.reverb,
                              dry_level=1 - 0.3 * fx.reverb, width=1.0))
    return Pedalboard(plugins) if plugins else None


def _mastered(bus: np.ndarray) -> np.ndarray:
    if Pedalboard is not None:
        bus = Pedalboard([Limiter(threshold_db=-3, release_ms=120)])(np.ascontiguousarray(bus.T), SAMPLE_RATE).T
    loudest = float(np.abs(bus).max()) if bus.size else 0.0
    if loudest > 0:
        bus = bus * (PEAK / loudest)
    return without_trailing_silence(bus, SAMPLE_RATE, keep_seconds=0.3)


def _active_rms(samples: np.ndarray, frame: int = 2048) -> float:
    """Loudness while the track is playing: rests and the silence after it don't count."""
    mono = np.abs(samples).max(axis=1) if samples.ndim == 2 else np.abs(samples)
    frames = len(mono) // frame
    if frames == 0:
        return float(np.sqrt(np.mean(mono ** 2))) if len(mono) else 0.0
    rms = np.sqrt(np.mean(mono[: frames * frame].reshape(frames, frame) ** 2, axis=1))
    active = rms[rms > max(rms.max() * 0.03, 1e-4)]
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else 0.0


def _db(value: float) -> float:
    return round(float(20 * np.log10(value)), 2) if value > 0 else -120.0


def _forget_old_stems(stem_dir: Path) -> None:
    stems = sorted(stem_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    for old in stems[:-MAX_STEMS_KEPT]:
        old.unlink(missing_ok=True)
