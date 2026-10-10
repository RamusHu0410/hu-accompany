"""Edits applied to a song project (hum/chat/executor.py): one test or more per command."""

import pytest

from hum.chat.commands import Edit
from hum.chat.executor import apply
from hum.song import ArrangeOptions, arrange
from hum.song.instruments import DRUM_KITS, INSTRUMENTS
from hum.transcription import tonic_pitch_class


@pytest.fixture(scope="module")
def song(sample):
    return arrange(sample, ArrangeOptions(preset="lofi"), hum="hum.wav")


def edit(project, **fields):
    return apply(project, [Edit(**fields)])


def notes_of(project, role):
    return [(n.pitch, n.start, n.duration) for n in project.track(role).notes]


# ── The mixer: nothing to render again ─────────────────────────────────


def test_volume_moves_by_the_amount_asked(song):
    quieter = edit(song, action="change_volume", part="drums", direction="down")
    slightly = edit(song, action="change_volume", part="drums", direction="down", amount="slight")
    assert quieter.project.track("drums").volume == pytest.approx(song.track("drums").volume - 0.2)
    assert slightly.project.track("drums").volume == pytest.approx(song.track("drums").volume - 0.1)
    assert quieter.changed == [] and quieter.mixed == ["drums"]
    assert quieter.label == "drums quieter"


def test_no_part_is_turned_up_past_the_melody(song):
    project = song
    for _ in range(2):  # 55% -> 90% -> stops just under the melody
        project = edit(project, action="change_volume", part="chords", direction="up", amount="strong").project
    assert project.track("chords").volume == pytest.approx(project.track("melody").volume - 0.05)
    again = edit(project, action="change_volume", part="chords", direction="up", amount="strong")
    assert again.done == [] and "melody" in again.refused[0]


def test_a_quieter_melody_takes_the_band_down_with_it(song):
    result = edit(song, action="change_volume", part="melody", direction="down", amount="strong")
    melody = result.project.track("melody").volume
    assert all(t.volume < melody for t in result.project.tracks if t.role != "melody")


def test_mute_unmute_solo_unsolo(song):
    muted = edit(song, action="mute", part="bass").project
    assert muted.track("bass").mute
    assert not edit(muted, action="unmute", part="bass").project.track("bass").mute
    soloed = edit(song, action="solo", part="drums").project
    assert [t.id for t in soloed.tracks if t.solo] == ["drums"]
    assert not any(t.solo for t in edit(soloed, action="unsolo").project.tracks)


def test_effects_change_one_part_or_all(song):
    wetter = edit(song, action="change_effect", effect="reverb", direction="up", part="melody")
    assert wetter.project.track("melody").effects.reverb > song.track("melody").effects.reverb
    assert wetter.mixed == ["melody"] and wetter.changed == []
    darker = edit(song, action="change_effect", effect="brightness", direction="down").project
    assert all(t.effects.eq_high < s.effects.eq_high for t, s in zip(darker.tracks, song.tracks))


# ── Instruments ────────────────────────────────────────────────────────


def test_an_instrument_swap_renders_only_that_part(song):
    result = edit(song, action="set_instrument", part="chords", instrument="strings")
    assert result.project.track("chords").program == INSTRUMENTS["strings"]
    assert "String" in result.project.track("chords").name
    assert result.changed == ["chords"]
    assert notes_of(result.project, "chords") == notes_of(song, "chords")


def test_drums_take_drum_kits_and_nothing_else(song):
    assert edit(song, action="set_instrument", part="drums", instrument="jazz kit").project.track("drums").program == DRUM_KITS["jazz kit"]
    refused = edit(song, action="set_instrument", part="drums", instrument="violin")
    assert refused.done == [] and "drum kit" in refused.refused[0]
    assert edit(song, action="set_instrument", part="bass", instrument="808 kit").done == []


# ── Tempo and key ──────────────────────────────────────────────────────


def test_tempo_by_words_and_by_number(song):
    faster = edit(song, action="change_tempo", direction="up").project
    assert faster.tempo == pytest.approx(song.tempo * 1.1, abs=0.1)
    assert edit(song, action="set_tempo", value=120).project.tempo == 120
    assert edit(song, action="set_tempo", value=900).project.tempo == 220  # clamped


def test_transposing_moves_every_pitched_note_but_not_the_drums(song):
    result = edit(song, action="transpose", value=3)
    assert tonic_pitch_class(result.project.tonic) == (tonic_pitch_class(song.tonic) + 3) % 12
    for role in ("melody", "chords", "bass"):
        assert [p + 3 for p, _, _ in notes_of(song, role)] == [p for p, _, _ in notes_of(result.project, role)]
    assert notes_of(result.project, "drums") == notes_of(song, "drums")
    assert "drums" not in result.changed


def test_set_key_takes_the_nearer_way(song):  # D -> G is up 5, not down 7
    result = edit(song, action="set_key", key="G")
    assert result.project.tonic == "G" and result.project.transpose == 5


def test_transposing_stops_at_an_octave(song):
    far = edit(song, action="transpose", value=12).project
    assert edit(far, action="transpose", value=1).done == []


# ── Re-arranging: genre, mood, parts, sections, energy ─────────────────


def test_a_new_genre_is_a_new_band(song):
    jazz = edit(song, action="set_genre", genre="jazz").project
    assert jazz.preset == "jazz" and jazz.track("bass").program == 32  # upright bass
    assert [n[0] for n in notes_of(jazz, "melody")] == [n[0] for n in notes_of(song, "melody")]  # the same tune


def test_a_new_mood_keeps_the_listeners_instruments_and_mix(song):
    custom = apply(song, [Edit(action="set_instrument", part="chords", instrument="strings"),
                          Edit(action="change_volume", part="drums", direction="down")]).project
    dark = edit(custom, action="set_mood", mood="dark").project
    assert dark.mood == "dark"
    assert dark.track("chords").program == INSTRUMENTS["strings"]
    assert dark.track("drums").volume == custom.track("drums").volume
    assert any(t.role == "pad" for t in dark.tracks)


def test_adding_and_removing_parts(song):
    padded = edit(song, action="add_part", part="pad")
    assert padded.changed == ["pad"]
    assert notes_of(padded.project, "melody") == notes_of(song, "melody")
    no_drums = edit(song, action="remove_part", part="drums").project
    assert "drums" not in [t.role for t in no_drums.tracks] and no_drums.removed == ["drums"]
    # a later re-arrangement doesn't bring them back
    assert "drums" not in [t.role for t in edit(no_drums, action="set_mood", mood="bright").project.tracks]
    assert "drums" in [t.role for t in edit(no_drums, action="add_part", part="drums").project.tracks]
    assert edit(song, action="remove_part", part="melody").done == []


def test_a_section_played_differently_changes_only_that_section(song):
    result = edit(song, action="regenerate_section", section="chorus")
    chorus, verse = result.project.section("chorus"), result.project.section("verse")
    assert chorus.variation == 1
    old = {c.bar: c for c in song.chords}
    new = {c.bar: c for c in result.project.chords}
    assert any(new[b] != old[b] for b in range(chorus.start_bar, chorus.start_bar + chorus.bars))
    assert all(new[b] == old[b] for b in range(verse.start_bar, verse.start_bar + verse.bars))
    assert "melody" not in result.changed  # the tune is untouched, so it isn't rendered again
    assert set(result.changed) <= {"chords", "bass", "pad", "drums"}


def test_energy_makes_the_verse_fuller(song):
    bigger = edit(song, action="change_energy", section="verse", direction="up").project
    assert bigger.section("verse").intensity == song.section("verse").intensity + 1
    assert edit(bigger, action="change_energy", section="verse", direction="up").done == []


# ── Several at once, and what's refused ────────────────────────────────


def test_several_edits_apply_in_order_and_a_refused_one_doesnt_stop_the_rest(song):
    result = apply(song, [
        Edit(action="change_volume", part="pad", direction="up"),  # there is no pad
        Edit(action="mute", part="drums"),
        Edit(action="change_tempo", direction="down", amount="slight"),
    ])
    assert result.done == ["drums muted", f"{round(song.tempo * 0.95)} bpm"]
    assert len(result.refused) == 1 and "no pad" in result.refused[0]


def test_the_original_project_is_never_changed(song):
    before = song.to_json()
    apply(song, [Edit(action="transpose", value=2), Edit(action="set_genre", genre="rock")])
    assert song.to_json() == before


def test_a_missing_field_is_a_question_not_a_crash(song):
    result = edit(song, action="change_volume", part="drums")
    assert result.done == [] and result.refused == ["Louder or quieter?"]
