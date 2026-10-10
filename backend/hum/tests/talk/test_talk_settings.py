"""Reading the song settings the app sends: labels, limits, the one lead. No network."""

import pytest

from hum.engine.talk.settings import DEFAULT_LEAD, PIANO, Part, SongSettings, clean_label


@pytest.mark.parametrize(("text", "expected"), [("Lo-Fi", "lo-fi"), ("drum & bass", "drum & bass"), ("rock!", None), (42, None), ("", None)])
def test_clean_label(text, expected):
    assert clean_label(text) == expected


def test_from_dict_reads_and_clamps_what_the_page_sends():
    violin = {"name": "violin", "role": "background", "level": "soft", "section": "end"}
    settings = SongSettings.from_dict(
        {"emotion": 1.4, "speed": 0, "pitch": 0.333, "style": "Jazz", "instruments": [PIANO_DICT, violin], "energy": {"end": -1}}
    )
    assert settings == SongSettings(emotion=1.0, speed=0.0, pitch=0.33, style="jazz", instruments=(PIANO, Part("violin", section="end")), energy=(0, -1))
    assert SongSettings.from_dict(None) == SongSettings()
    assert SongSettings.from_dict({}).to_dict() == {
        "emotion": 0.5,
        "speed": 0.5,
        "pitch": 0.5,
        "style": None,
        "instruments": [SYNTH_DICT],
        "energy": {"start": 0, "end": 0},
    }


def test_from_dict_always_gives_the_song_one_lead():
    no_lead = SongSettings.from_dict({"instruments": [{"name": "violin", "role": "background", "level": "soft", "section": "end"}]})
    assert no_lead.instruments == (Part("violin", "lead", "soft", "all"),)  # the lead plays the whole song
    only_drums = SongSettings.from_dict({"instruments": [{"name": "drums", "role": "lead", "level": "soft", "section": "all"}]})
    assert only_drums.instruments == (DEFAULT_LEAD, Part("drums"))
    assert SongSettings.from_dict({"instruments": []}).instruments == (DEFAULT_LEAD,)


PIANO_DICT = {"name": "piano", "role": "lead", "level": "normal", "section": "all"}
SYNTH_DICT = {"name": "synth", "role": "lead", "level": "normal", "section": "all"}


@pytest.mark.parametrize(
    "bad",
    [
        {"speed": "fast"},
        {"speed": True},
        {"pitch": float("nan")},
        {"instruments": "drums"},
        {"instruments": ["drums"]},
        {"instruments": [{**PIANO_DICT, "level": "deafening"}]},
        {"instruments": [{**PIANO_DICT, "name": "<script>"}]},
        {"energy": {"end": 3}},
        {"energy": {"start": 0.5}},
        {"energy": [1, 1]},
        ["not", "a", "dict"],
    ],
)
def test_from_dict_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        SongSettings.from_dict(bad)
