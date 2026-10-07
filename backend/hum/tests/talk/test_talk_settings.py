"""The settings arithmetic: steps, limits, resets, styles and instruments. No network."""

import pytest

from hum.engine.talk.commands import Adjustment, Change, Command, NewInstrument
from hum.engine.talk.settings import DEFAULT_LEAD, PIANO, Part, SongSettings, apply_command, blocked_adjustments, changed_fields, clean_label, move_dial


def command(*changes, style=None, add=(), remove=(), change=()):
    adjustments = [Adjustment(setting=s, direction=d, amount=a) for s, d, a in changes]
    new = [NewInstrument(instrument=name) for name in add]
    return Command(intent="adjust", adjustments=adjustments, style=style, add=new, remove=list(remove), change=list(change), reply="ok")


@pytest.mark.parametrize(
    ("start", "direction", "amount", "expected"),
    [
        (0.5, "up", "slight", 0.6),
        (0.5, "down", "moderate", 0.3),
        (0.5, "up", "strong", 0.85),
        (0.2, "down", "strong", 0.0),  # stops at the bottom
        (0.95, "up", "moderate", 1.0),  # stops at the top
        (0.3, "up", "max", 1.0),
        (0.7, "down", "max", 0.0),
        (0.9, "reset", "moderate", 0.5),
        (0.1, "up", "slight", 0.2),  # no 0.20000000000000001
    ],
)
def test_move_dial(start, direction, amount, expected):
    assert move_dial(start, direction, amount) == expected


def test_relative_changes_build_on_the_current_settings():
    now = SongSettings(emotion=0.5, speed=0.7, pitch=0.5)
    after = apply_command(now, command(("speed", "up", "moderate"), ("emotion", "up", "slight")))
    assert (after.speed, after.emotion, after.pitch) == (0.9, 0.6, 0.5)
    assert changed_fields(now, after) == ["emotion", "speed"]


def test_style_and_instruments():
    # apply_command gets names already checked by edits.check, so it simply applies them
    after = apply_command(SongSettings(instruments=(PIANO, Part("violin"))), command(style="  Rock ", add=["drums", "drums"], remove=["violin"]))
    assert after.style == "rock"
    assert after.instruments == (PIANO, Part("drums"))
    assert changed_fields(SongSettings(), after) == ["style", "instruments"]


def test_bad_style_is_ignored():
    assert apply_command(SongSettings(style="jazz"), command(style="<script>")).style == "jazz"


@pytest.mark.parametrize(("level", "step", "expected"), [("soft", "louder", "normal"), ("normal", "louder", "loud"), ("loud", "louder", "loud"), ("soft", "softer", "soft")])
def test_levels_step_and_stop_at_the_ends(level, step, expected):
    song = SongSettings(instruments=(PIANO, Part("violin", level=level)))
    assert apply_command(song, command(change=[Change(instrument="violin", level=step)])).instruments[1].level == expected


@pytest.mark.parametrize(("text", "expected"), [("Lo-Fi", "lo-fi"), ("drum & bass", "drum & bass"), ("rock!", None), (42, None), ("", None)])
def test_clean_label(text, expected):
    assert clean_label(text) == expected


def test_a_song_holds_at_most_six_instruments():
    settings = SongSettings(instruments=(PIANO, *(Part(f"old {n}") for n in range(4))))
    after = apply_command(settings, command(add=["new 1", "new 2", "new 3"]))
    assert [part.name for part in after.instruments] == ["piano", "old 0", "old 1", "old 2", "old 3", "new 1"]


def test_blocked_adjustments_find_changes_that_did_nothing():
    at_top = SongSettings(speed=1.0)
    blocked = blocked_adjustments(at_top, command(("speed", "up", "moderate"), ("pitch", "up", "slight")))
    assert [(b.setting, b.direction) for b in blocked] == [("speed", "up")]


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
