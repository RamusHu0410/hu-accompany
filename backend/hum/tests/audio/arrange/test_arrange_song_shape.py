"""The song's shape around a hum (transforms.fill and transforms.frame): a short tune filled out,
an introduction that builds into it, and an ending that lets the last chord ring. This is what
makes a 3-bar hum sound like the 8-bar test melody, with build-ups."""

from pathlib import Path

import pytest

from hum.engine.audio.arrange import arranged_melody
from hum.engine.audio.arrange import orchestrate as O
from hum.engine.audio.arrange.config import CRASH, STYLES
from hum.engine.audio.arrange.ensembles import ENSEMBLES, choose
from hum.engine.audio.arrange.melody import Note, load_melody
from hum.engine.audio.arrange.transforms import fill, frame

HUM = load_melody(Path(__file__).resolve().parents[2] / "fixtures" / "hum_sample.melody.json")  # part A's real 3-bar hum


def _bars_long(melody, bars):
    return melody.with_notes([Note(60 + i % 5, float(i), 1.0) for i in range(int(bars * 4))])


@pytest.mark.parametrize("length, filled, sections", [(1, 8, tuple(range(8))), (2, 8, (0, 2, 4, 6)), (3, 8, (0, 4)),
                                                      (4, 8, (0, 4)), (6, 8, ()), (10, 12, ())])
def test_fill(melody, length, filled, sections):
    out = fill(_bars_long(melody, length), 8)
    assert out.bars == filled
    assert out.sections == sections


def test_frame(melody):
    framed = frame(melody, 2, 1)
    assert framed.bars == melody.bars + 3
    assert framed.notes[0].start_beats == 8.0  # after a 2-bar introduction
    assert framed.sections == (0, 2, melody.bars + 2)
    assert max(n.end_beats for n in framed.notes) <= (framed.bars - 1) * 4  # the last bar has no tune


@pytest.mark.parametrize("style", sorted(STYLES))
def test_a_short_hum_becomes_a_whole_song(style):
    song, _, _ = arranged_melody(HUM, style)
    preset = STYLES[style]
    assert song.bars >= 8 + preset.intro_bars + preset.outro_bars
    assert song.notes[0].start_beats == preset.intro_bars * song.beats_per_bar or preset.intro_bars == 0


@pytest.mark.parametrize("ensemble", sorted(ENSEMBLES))
def test_the_introduction_builds_into_the_tune_and_the_ending_rings(ensemble):
    song, _, _ = arranged_melody(HUM, "cinematic")
    _, orchestration, _ = choose(STYLES["cinematic"], ensemble, 1)
    midi, _ = O.orchestrate(song, orchestration)
    tracks = {i.name: i for i in midi.instruments}
    bar = song.beats_per_bar * song.seconds_per_beat
    entrance = song.notes[0].start_beats / song.beats_per_bar * bar

    assert all(n.start >= entrance - 1e-6 for n in tracks["melody"].notes)
    playing_before = {name for name, t in tracks.items() if any(n.start < entrance for n in t.notes)}
    assert {"strings_pad", "figure", "bass", "percussion"} <= playing_before  # the band plays the intro
    crashes = [n.start for n in tracks["percussion"].notes if n.pitch == CRASH]
    assert any(abs(t - entrance) < 1e-6 for t in crashes)  # and lands on the tune's first note

    last_bar = (song.bars - 1) * bar
    assert all(n.end <= last_bar + 1e-6 for n in tracks["melody"].notes)
    ringing = [n for n in tracks["strings_pad"].notes if n.start >= last_bar - 1e-6]
    assert ringing and any(abs(t - last_bar) < 1e-6 for t in crashes)
