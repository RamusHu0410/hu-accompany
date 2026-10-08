"""A project as sound and as MIDI (hum/song/render.py). The audio tests need FluidSynth and a
soundfont, and skip without them."""

import io
import shutil

import mido
import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from hum import rawplay
from hum.engine.accompanist.audio.render import find_soundfont
from hum.song import ArrangeOptions, arrange, export_midi, mix
from hum.song import render as render_module
from hum.song.render import swung


def can_render() -> bool:
    try:
        find_soundfont()
    except FileNotFoundError:
        return False
    return shutil.which("fluidsynth") is not None


needs_fluidsynth = pytest.mark.skipif(not can_render(), reason="needs FluidSynth and a soundfont")


@pytest.fixture
def stems(tmp_path):
    return tmp_path / "stems"


def test_swing_pushes_only_the_off_beat_eighths():
    assert swung(3.0, 0.6) == 3.0
    assert swung(3.5, 0.6) == pytest.approx(3.6)
    assert swung(3.25, 0.6) == pytest.approx(3.3)
    assert swung(3.5, 0.5) == 3.5


def test_the_midi_export_has_every_track(sample):
    project = arrange(sample, ArrangeOptions(preset="cinematic"))
    data = export_midi(project)

    mido.MidiFile(file=io.BytesIO(data))  # a valid file
    midi = pretty_midi.PrettyMIDI(io.BytesIO(data))
    assert [i.name for i in midi.instruments] == [t.name for t in project.tracks]
    for exported, track in zip(midi.instruments, project.tracks):
        assert len(exported.notes) == len(track.notes)
        assert exported.is_drum == track.is_drums
        assert exported.program == track.program
    assert midi.get_tempo_changes()[1][0] == pytest.approx(project.tempo, abs=0.5)
    assert midi.get_end_time() == pytest.approx(project.length_seconds, abs=0.5)


@needs_fluidsynth
@pytest.mark.parametrize("preset", ["lofi", "cinematic", "rock", "jazz"])
def test_the_melody_is_the_loudest_part_of_the_mix(sample, stems, preset):
    project = arrange(sample, ArrangeOptions(preset=preset))
    result = mix(project, stems)

    audio, rate = sf.read(io.BytesIO(result.wav))
    assert audio.shape[1] == 2
    assert np.abs(audio).max() == pytest.approx(rawplay.PEAK, abs=0.01)
    assert project.length_seconds <= len(audio) / rate <= project.length_seconds + 3
    melody = result.levels.pop("melody")
    assert all(melody - level >= 3 for level in result.levels.values()), result.levels  # at least 3 dB on top


@needs_fluidsynth
def test_only_what_changed_is_rendered_again(sample, stems):
    project = arrange(sample, ArrangeOptions(preset="pop"))
    first = mix(project, stems)
    assert sorted(first.rendered) == sorted(t.id for t in project.tracks)

    project.track("chords").volume = 0.2
    project.track("drums").effects.reverb = 0.8
    project.track("bass").pan = -0.5
    assert mix(project, stems).rendered == []  # mixer settings render nothing

    project.track("chords").notes.pop()
    again = mix(project, stems)
    assert again.rendered == ["chords"]
    assert "melody" in again.reused


@needs_fluidsynth
def test_mute_and_solo_decide_what_is_heard(sample, stems):
    project = arrange(sample, ArrangeOptions(preset="pop"))
    project.track("drums").mute = True
    assert "drums" not in mix(project, stems).levels
    project.track("bass").solo = True
    assert list(mix(project, stems).levels) == ["bass"]


@needs_fluidsynth
def test_old_stems_are_cleared_out(sample, stems, monkeypatch):
    monkeypatch.setattr(render_module, "MAX_STEMS_KEPT", 3)
    mix(arrange(sample, ArrangeOptions(preset="pop")), stems)
    assert len(list(stems.glob("*.wav"))) == 3


def test_without_fluidsynth_it_says_so(sample, stems, monkeypatch):
    def missing():
        raise FileNotFoundError("no soundfont")

    monkeypatch.setattr(render_module, "find_soundfont", missing)
    with pytest.raises(rawplay.RenderUnavailable):
        mix(arrange(sample), stems)
