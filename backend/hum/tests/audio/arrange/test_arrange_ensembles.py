"""Who plays the song (ensembles.py): an orchestra, a band, electronic instruments or a chamber group,
picked per song by a seed, so each new song can sound different."""

from collections import Counter

import pytest

from hum.engine.audio.arrange import ArrangeSettings, arrange_and_render
from hum.engine.audio.arrange import orchestrate as O
from hum.engine.audio.arrange.config import CLOSED_HAT, INSTRUMENT_RANGES, KICK, RIDE, STYLES
from hum.engine.audio.arrange.ensembles import ENSEMBLES, choose, ensemble_for_word
from hum.engine.audio.arrange.melody import key_pitch_classes
from hum.engine.audio.arrange.transforms import apply_operations

from conftest import FIXTURE_JSON

D_MINOR = key_pitch_classes("D minor")


def test_without_a_variation_a_style_keeps_its_own_orchestra():
    for style in STYLES.values():
        assert choose(style) == ("orchestra", style.orchestration, 1.0)


def test_the_same_seed_gives_the_same_band_and_new_seeds_give_every_kind():
    style = STYLES["cinematic"]
    assert choose(style, None, 42) == choose(style, None, 42)
    kinds = Counter(choose(style, None, seed)[0] for seed in range(40))
    assert set(kinds) == set(ENSEMBLES) and min(kinds.values()) >= 5
    combos = {repr(choose(style, None, seed)[1]) for seed in range(40)}
    assert len(combos) >= 30  # instruments vary within an ensemble too


def test_a_named_ensemble_is_used():
    assert all(choose(STYLES["pop"], name, seed)[0] == name for name in ENSEMBLES for seed in range(5))
    with pytest.raises(ValueError):
        ArrangeSettings(ensemble="polka")


def test_the_swell_is_a_different_instrument_from_the_tune():
    for name in ENSEMBLES:
        for seed in range(20):
            _, o, _ = choose(STYLES["cinematic"], name, seed)
            assert o.brass not in (o.lead, o.double)


@pytest.mark.parametrize("word, ensemble", [("rock", "band"), ("Lo-fi", "electronic"), ("digital", "electronic"),
                                            ("acoustic", "chamber"), ("epic", "orchestra"), ("cinematic", None), (None, None)])
def test_words_that_ask_for_an_ensemble(word, ensemble):
    assert ensemble_for_word(word) == ensemble


@pytest.mark.parametrize("style", sorted(STYLES))
@pytest.mark.parametrize("ensemble", sorted(ENSEMBLES))
def test_every_ensemble_plays_every_style_well(melody, style, ensemble):
    tune = apply_operations(melody, STYLES[style].transforms)
    for seed in range(3):
        _, orchestration, _ = choose(STYLES[style], ensemble, seed)
        midi, _ = O.orchestrate(tune, orchestration)
        tracks = {i.name: i for i in midi.instruments}
        assert list(tracks) == O.track_names(orchestration)
        for name, track in tracks.items():
            assert track.notes, name
            if track.is_drum:
                continue
            low, high = INSTRUMENT_RANGES[track.program]
            assert all(low <= n.pitch <= high for n in track.notes), (name, track.program)
            if name not in ("melody", "melody_double"):
                assert {n.pitch % 12 for n in track.notes} <= D_MINOR, name
        bar = tune.beats_per_bar * tune.seconds_per_beat
        for b in range(tune.bars):
            assert len({i.name for i in midi.instruments for n in i.notes if n.start < (b + 1) * bar and n.end > b * bar}) >= 4


def _drums(melody, ensemble):
    _, orchestration, _ = choose(STYLES["cinematic"], ensemble, 0)
    midi, _ = O.orchestrate(melody, orchestration)
    return orchestration, next(i for i in midi.instruments if i.is_drum)


def test_each_ensemble_has_its_own_drums(melody):
    beat = melody.seconds_per_beat
    electronic, drums = _drums(melody, "electronic")
    kicks = {round(n.start / beat, 3) for n in drums.notes if n.pitch == KICK}
    assert kicks == {float(b) for b in range(melody.bars * 4)}  # four on the floor
    assert electronic.kit in (24, 25)

    band, drums = _drums(melody, "band")
    assert {n.pitch for n in drums.notes} >= {O.config.LOW_TOM, O.config.MID_TOM, O.config.HIGH_TOM, CLOSED_HAT}  # fills
    assert band.kit in (0, 16)

    chamber, drums = _drums(melody, "chamber")
    assert chamber.kit == 40 and any(n.pitch == RIDE for n in drums.notes)  # brushes and ride


def test_the_run_records_who_played(tmp_path, fake_render):
    result = arrange_and_render(str(FIXTURE_JSON), "pop", str(tmp_path), ArrangeSettings(ensemble="electronic", variation=7))
    assert result.ensemble == "electronic"
    orchestrate_step = next(s for s in result.steps if s.step == "orchestrate")
    assert orchestrate_step.info["ensemble"] == "electronic"
    assert orchestrate_step.info["instruments"]["percussion"] in ("electronic kit", "TR-808 kit")
