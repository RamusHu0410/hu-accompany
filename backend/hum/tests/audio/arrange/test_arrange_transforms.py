"""Each transformation on the fixture, and the style presets that chain them."""

import pytest

from hum.engine.audio.arrange import transforms as T
from hum.engine.audio.arrange.config import STYLES
from hum.engine.audio.arrange.melody import from_stream, key_pitch_classes, to_stream

D_MINOR = key_pitch_classes("D minor")


def run(melody, name, **params):
    return T.apply_operations(melody, [(name, params)])


def triples(notes):
    return [(n.pitch, n.start_beats, n.duration_beats) for n in notes]


def degree(pitch):
    return T.scale_ladder("D minor").index(pitch)


def test_repeat(melody):
    out = run(melody, "repeat", times=2)
    assert len(out.notes) == 2 * len(melody.notes)
    assert triples(out.notes[:28]) == triples(melody.notes)
    assert triples(out.notes[28:]) == [(p, s + 32, d) for p, s, d in triples(melody.notes)]


def test_augment_and_diminish(melody):
    wide = run(melody, "augment", factor=2)
    assert triples(wide.notes) == [(p, s * 2, d * 2) for p, s, d in triples(melody.notes)]
    narrow = run(melody, "diminish", factor=2)
    assert triples(narrow.notes) == [(p, s / 2, d / 2) for p, s, d in triples(melody.notes)]


def test_transpose_moves_every_note_one_scale_degree(melody):
    out = run(melody, "transpose", steps=1)
    assert [degree(n.pitch) for n in out.notes] == [degree(n.pitch) + 1 for n in melody.notes]
    assert {n.pitch % 12 for n in out.notes} <= D_MINOR
    assert [n.start_beats for n in out.notes] == [n.start_beats for n in melody.notes]


def test_octave(melody):
    assert [n.pitch for n in run(melody, "octave", octaves=-1).notes] == [n.pitch - 12 for n in melody.notes]


def test_sequence_climbs_the_opening_figure_then_plays_the_tune(melody):
    out = run(melody, "sequence", bars=1, steps=[1, 2])
    figure = [n for n in melody.notes if n.start_beats < 4]
    for i, step in enumerate([0, 1, 2]):
        section = [n for n in out.notes if 4 * i <= n.start_beats < 4 * (i + 1)]
        assert [degree(n.pitch) for n in section] == [degree(n.pitch) + step for n in figure]
        assert [n.start_beats - 4 * i for n in section] == [n.start_beats for n in figure]
    assert triples([n for n in out.notes if n.start_beats >= 12]) == [(p, s + 12, d) for p, s, d in triples(melody.notes)]


def test_additive_builds_up_the_opening_bar_then_plays_the_tune(melody):
    """arvo's additive process: D; D E; D E F; D E F G. The tune follows on a bar line."""
    out = run(melody, "additive", bars=1)
    build = [n for n in out.notes if n.start_beats < 12]
    assert [n.pitch for n in build] == [62, 62, 64, 62, 64, 65, 62, 64, 65, 67]
    tune = [n for n in out.notes if n.start_beats >= 12]
    assert tune[0].start_beats % 4 == 0
    assert triples(tune) == [(p, s + tune[0].start_beats, d) for p, s, d in triples(melody.notes)]


def test_restate_ends_on_the_last_phrase_an_octave_up(melody):
    out = run(melody, "restate", bars=4, steps=7)
    assert out.bars == 12
    last_phrase = [n for n in melody.notes if n.start_beats >= 16]
    assert triples([n for n in out.notes if n.start_beats >= 32]) == [(p + 12, s + 16, d) for p, s, d in triples(last_phrase)]


def test_operations_leave_their_input_alone(melody):
    part = to_stream(melody)
    for name, params in [("repeat", {}), ("transpose", {"steps": 2, "key": "D minor"}), ("additive", {}),
                         ("sequence", {"key": "D minor"}), ("restate", {"key": "D minor"}), ("augment", {})]:
        T.OPERATIONS[name](part, bpb=4.0, **params)
        assert from_stream(part, melody) == melody, name


def test_diatonic_shift():
    assert T.diatonic_shift(62, 7, "D minor") == 74  # an octave
    assert T.diatonic_shift(62, 2, "D minor") == 65  # D -> F
    assert T.diatonic_shift(61, 1, "D minor") == 63  # C# (not in the scale) keeps its offset from C
    with pytest.raises(ValueError):
        T.diatonic_shift(126, 5, "D minor")


@pytest.mark.parametrize("style", sorted(STYLES))
def test_every_style_stays_in_key_and_on_bar_lines(melody, style):
    out = T.apply_operations(melody, STYLES[style].transforms)
    assert {n.pitch % 12 for n in out.notes} <= D_MINOR
    assert out.bars <= T.MAX_BARS
    assert out.notes[0].start_beats == 0


def test_unknown_operation_is_refused(melody):
    with pytest.raises(ValueError, match="Unknown transformation"):
        T.apply_operations(melody, [("reverse", {})])


def test_too_long_is_refused(melody):
    with pytest.raises(ValueError, match="more than 32"):
        T.apply_operations(melody, [("repeat", {"times": 5})])


def test_fit_pitches_keeps_the_shape():
    line = [62, 67, 74, 69]
    fitted = T.fit_pitches(line, 55, 100)
    assert all(55 <= p <= 100 for p in fitted)
    assert [b - a for a, b in zip(fitted, fitted[1:])] == [b - a for a, b in zip(line, line[1:])]
    assert T.fit_pitches([30, 90], 40, 60) == [42, 54]  # folded in by octaves when the span is too wide


def test_arvo_needs_the_flat_shim():
    """Why _ArvoStream exists: music21 10 has no Stream.flat, which arvo 0.3.0 calls."""
    from music21 import stream

    assert not hasattr(stream.Stream(), "flat")
    assert hasattr(T._ArvoStream(), "flat")


@pytest.mark.parametrize("operations, sections", [
    ([], (0,)),
    ([("repeat", {"times": 2})], (0, 8)),
    ([("additive", {"bars": 1})], (0, 3)),  # a 3-bar build-up, then the tune
    ([("sequence", {"bars": 1, "steps": [1, 2]})], (0, 3)),
    ([("restate", {"bars": 4})], (0, 8)),
    ([("augment", {"factor": 2}), ("restate", {"bars": 4})], (0, 16)),
    ([("additive", {}), ("repeat", {"times": 2})], (0, 3, 11, 14)),
])
def test_sections_mark_where_each_part_begins(melody, operations, sections):
    assert T.apply_operations(melody, operations).sections == sections


def test_sections_survive_the_json_round_trip(melody, tmp_path):
    from hum.engine.audio.arrange.melody import load_melody, save_melody_json

    out = T.apply_operations(melody, [("additive", {})])
    assert load_melody(save_melody_json(out, tmp_path / "t.json")) == out
    assert "sections" not in melody.to_dict()  # the contract's melody.json doesn't get the field
