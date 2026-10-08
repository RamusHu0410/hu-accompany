"""A listener's settings (ArrangeSettings) on top of a style: tempo, key, mode, instruments, energy."""

import pytest

from hum.engine.audio.arrange import ArrangeSettings, ExtraPart
from hum.engine.audio.arrange import orchestrate as O
from hum.engine.audio.arrange.config import STYLES
from hum.engine.audio.arrange.melody import key_pitch_classes
from hum.engine.audio.arrange.transforms import apply_settings, fit_pitches


def test_default_settings_change_nothing(melody):
    assert apply_settings(melody, ArrangeSettings()) == melody
    plain, _ = O.orchestrate(melody, STYLES["cinematic"].orchestration)
    same, _ = O.orchestrate(melody, STYLES["cinematic"].orchestration, ArrangeSettings())
    assert [(i.name, i.program, [(n.pitch, n.velocity) for n in i.notes]) for i in plain.instruments] == \
           [(i.name, i.program, [(n.pitch, n.velocity) for n in i.notes]) for i in same.instruments]


def test_tempo_scale(melody):
    assert apply_settings(melody, ArrangeSettings(tempo_scale=1.5)).tempo_bpm == 138.0
    assert apply_settings(melody, ArrangeSettings(tempo_scale=0.5)).tempo_bpm == 46.0


def test_transposition_moves_the_key_too(melody):
    up = apply_settings(melody, ArrangeSettings(transpose=3))
    assert up.key == "F minor"
    assert [n.pitch for n in up.notes] == [n.pitch + 3 for n in melody.notes]
    assert {n.pitch % 12 for n in up.notes} <= key_pitch_classes("F minor")


def test_major_moves_each_degree_to_the_major_scale(melody):
    bright = apply_settings(melody, ArrangeSettings(mode="major"))
    assert bright.key == "D major"
    moved = {a.pitch: b.pitch for a, b in zip(melody.notes, bright.notes) if a.pitch != b.pitch}
    assert moved == {65: 66, 70: 71, 72: 73}  # F -> F#, Bb -> B, C -> C#
    assert {n.pitch % 12 for n in bright.notes} <= key_pitch_classes("D major")
    assert apply_settings(bright, ArrangeSettings(mode="minor")) == melody  # and back


def test_an_octave_up_is_still_heard_in_the_lead():
    line = [62, 65, 69, 74]
    assert fit_pitches(line, 55, 100, bias=12)[0] == fit_pitches(line, 55, 100)[0] + 12


def test_lead_instrument_and_volume(melody):
    midi, _ = O.orchestrate(melody, STYLES["cinematic"].orchestration, ArrangeSettings(lead=89, lead_volume=127))
    lead = midi.instruments[0]
    assert lead.name == "melody" and lead.program == 89
    assert [cc.value for cc in lead.control_changes if cc.number == 7] == [127]


def test_extra_parts_play_only_in_their_section(melody):
    settings = ArrangeSettings(parts=(ExtraPart(42, "bass", 90, "end"), ExtraPart(0, "drums", 50, "start"),
                                      ExtraPart(52, "chords", 70, "all")))
    midi, _ = O.orchestrate(melody, STYLES["piano"].orchestration, settings)
    tracks = {i.name: i for i in midi.instruments}
    assert list(tracks)[:len(O.TRACKS)] == O.track_names(STYLES["piano"].orchestration)
    half = melody.bars * melody.beats_per_bar / 2 * melody.seconds_per_beat
    cello, drums, choir = tracks["extra_1_bass"], tracks["extra_2_drums"], tracks["extra_3_chords"]
    assert cello.program == 42 and all(n.start >= half - 1e-6 for n in cello.notes) and cello.notes
    assert drums.is_drum and all(n.start < half for n in drums.notes) and drums.notes
    assert choir.program == 52 and choir.notes[0].start == 0
    assert {n.pitch % 12 for n in cello.notes + choir.notes} <= key_pitch_classes("D minor")


def test_energy_makes_each_half_softer_or_louder(melody):
    plain, _ = O.orchestrate(melody, STYLES["piano"].orchestration)
    shaped, _ = O.orchestrate(melody, STYLES["piano"].orchestration, ArrangeSettings(energy=(-2, 2)))
    half = melody.bars * melody.beats_per_bar / 2 * melody.seconds_per_beat
    for a, b in zip(plain.instruments[0].notes, shaped.instruments[0].notes):
        if a.velocity < 100:
            assert (b.velocity < a.velocity) if a.start < half else (b.velocity > a.velocity)


@pytest.mark.parametrize("bad", [dict(tempo_scale=3), dict(transpose=13), dict(mode="dorian"), dict(energy=(3, 0))])
def test_out_of_range_settings_are_refused(bad):
    with pytest.raises(ValueError):
        ArrangeSettings(**bad)
