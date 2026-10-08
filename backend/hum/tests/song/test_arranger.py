"""The hum arranged as a song (hum/song/arranger.py), the genres and moods that shape it
(hum/song/presets.py), and the project it's held in (hum/song/project.py)."""

import pytest

from hum.song import ArrangeOptions, Project, arrange, arrange_phrase, options_from_page
from hum.song.drums import CRASH, KICK
from hum.song.presets import MOODS, PRESETS, feel_tempo, preset_for
from hum.transcription import SCALES, HeardNote, Transcription, tonic_pitch_class

PITCHED = ("chords", "bass", "pad")


def song(sample, **options) -> Project:
    return arrange(sample, ArrangeOptions(**options))


def notes_in(project, role, section):
    s = project.section(section)
    track = next((t for t in project.tracks if t.role == role), None)
    return [n for n in (track.notes if track else []) if s.start <= n.start < s.end]


# ── Structure ──────────────────────────────────────────────────────────


def test_the_song_runs_intro_verse_chorus_outro_without_gaps(sample):
    project = song(sample)
    assert [s.name for s in project.sections] == ["intro", "verse", "chorus", "outro"]
    for before, after in zip(project.sections, project.sections[1:]):
        assert after.start_bar == before.start_bar + before.bars
    assert project.section("verse").bars >= 4
    assert len(project.chords) == project.bars


def test_verse_and_chorus_carry_the_hum_note_for_note(sample):
    project = song(sample)
    tune = sample.quantized()
    for section in ("verse", "chorus"):
        played = notes_in(project, "melody", section)
        start = project.section(section).start
        first = played[: len(tune)]
        lift = first[0].pitch - tune[0].pitch
        assert lift % 12 == 0  # moved by whole octaves only
        assert [n.pitch - lift for n in first] == [n.pitch for n in tune]
        assert [n.start - start for n in first] == pytest.approx([n.start for n in tune])
        assert [n.duration for n in first] == pytest.approx([n.duration for n in tune])
    assert not notes_in(project, "melody", "intro") and not notes_in(project, "melody", "outro")


def test_arranging_leaves_the_raw_transcription_alone(sample):
    before = list(sample.raw)
    for preset in PRESETS:
        arrange(sample, ArrangeOptions(preset=preset, transpose=3))
    assert sample.raw == before


# ── The melody on top ──────────────────────────────────────────────────


@pytest.mark.parametrize("preset", list(PRESETS))
@pytest.mark.parametrize("mood", ["neutral", "dark"])
def test_the_melody_is_always_the_highest_and_loudest_part(sample, preset, mood):
    project = song(sample, preset=preset, mood=mood)
    melody = project.track("melody")
    lowest_tune = min(n.pitch for n in melody.notes)
    for track in project.tracks:
        if track.role in PITCHED:
            assert max(n.pitch for n in track.notes) < lowest_tune, track.id
        if track.role != "melody":
            assert track.volume < melody.volume


def test_a_low_hum_is_lifted_into_a_lead_register(sample):
    project = song(sample)
    assert min(n.pitch for n in project.track("melody").notes) >= 60
    assert min(n.pitch for n in sample.raw) < 60  # it was hummed below middle C


# ── Key, chords, bass ──────────────────────────────────────────────────


@pytest.mark.parametrize("preset", list(PRESETS))
def test_every_pitched_note_is_in_the_detected_key(sample, preset):
    project = song(sample, preset=preset)
    assert (project.tonic, project.mode) == (sample.tonic, sample.mode)
    scale = {(tonic_pitch_class(project.tonic) + step) % 12 for step in SCALES[project.mode]}
    for track in project.tracks:
        if track.role != "drums":
            assert {n.pitch % 12 for n in track.notes} <= scale, track.id


def test_the_bass_plays_each_bars_root_on_the_downbeat(sample):
    project = song(sample)
    bass = project.track("bass").notes
    for chord in project.chords:
        downbeat = [n for n in bass if n.start == chord.bar * 4]
        if downbeat:
            assert downbeat[0].pitch % 12 == chord.root
    assert max(n.pitch for n in bass) < min(n.pitch for n in project.track("chords").notes)


def test_the_outro_comes_home(sample):
    project = song(sample)
    tonic = tonic_pitch_class(project.tonic)
    assert project.chords[-1].root == tonic
    assert project.chords[-2].degree in ("V", "iv", "IV")


def test_transposing_moves_the_key_and_the_tune(sample):
    plain, up = song(sample), song(sample, transpose=5)
    assert tonic_pitch_class(up.tonic) == (tonic_pitch_class(plain.tonic) + 5) % 12
    a = [n.pitch for n in plain.track("melody").notes]
    b = [n.pitch for n in up.track("melody").notes]
    assert all((y - x) % 12 == 5 for x, y in zip(a, b))


# ── Drums and tempo ────────────────────────────────────────────────────


def test_drums_sit_on_the_grid_and_get_bigger_in_the_chorus(sample):
    project = song(sample)
    drums = project.track("drums").notes
    assert all(abs(n.start * 4 - round(n.start * 4)) < 1e-9 for n in drums)
    assert not notes_in(project, "drums", "intro")  # pop starts with the band, no drums
    verse, chorus = project.section("verse"), project.section("chorus")
    per_bar = lambda s: len(notes_in(project, "drums", s.name)) / s.bars  # noqa: E731
    assert per_bar(chorus) > per_bar(verse)
    assert any(n.pitch == CRASH and n.start == chorus.start for n in drums)
    for bar in range(verse.start_bar, verse.start_bar + verse.bars):
        assert any(n.pitch == KICK and bar * 4 <= n.start < bar * 4 + 4 for n in drums)


def test_the_last_bar_is_one_hit_and_ringing_chords(sample):
    project = song(sample)
    last = (project.bars - 1) * 4
    assert sorted(n.pitch for n in project.track("drums").notes if n.start >= last) == sorted([KICK, CRASH])
    assert all(n.start == last and n.duration == 4 for n in project.track("chords").notes if n.start >= last)


@pytest.mark.parametrize("preset", list(PRESETS))
def test_each_genre_plays_at_its_own_tempo(sample, preset):
    project = song(sample, preset=preset)
    low, high = PRESETS[preset].tempo_range
    if low <= sample.tempo_bpm <= high:
        assert project.tempo == pytest.approx(sample.tempo_bpm, abs=0.1)
    else:  # pulled toward the genre's range, never further than the nudge allows
        assert abs(project.tempo - sample.tempo_bpm) <= sample.tempo_bpm * 0.12 + 0.1
        assert abs(project.tempo - (low + high) / 2) < abs(sample.tempo_bpm - (low + high) / 2)


def test_a_slow_hum_goes_double_time_in_a_fast_genre():
    preset, neutral = PRESETS["electronic"], MOODS["neutral"]
    assert feel_tempo(62, preset, neutral) == (124.0, 2.0)
    assert feel_tempo(240, PRESETS["lofi"], neutral) == (105.6, 0.5)  # half time is 120: pulled 12% toward 90
    assert feel_tempo(80, PRESETS["ballad"], neutral) == (80.0, 1.0)


def test_double_time_stretches_the_tune_onto_the_new_beat():
    hum = Transcription([HeardNote(60, 0, 0.5, 90), HeardNote(62, 0.5, 0.5, 90), HeardNote(64, 1.0, 1.0, 90)], 62.0, "C", "major")
    project = arrange(hum, ArrangeOptions(preset="electronic"))
    played = notes_in(project, "melody", "verse")[:3]
    start = project.section("verse").start
    assert [n.start - start for n in played] == [0, 1, 2]  # half-beats at 62 are whole beats at 124


# ── Genres and moods ───────────────────────────────────────────────────


@pytest.mark.parametrize("preset", list(PRESETS))
def test_each_genre_plays_with_its_own_small_band(sample, preset):
    palette = PRESETS[preset].palette
    project = song(sample, preset=preset)
    programs = {t.role: t.program for t in project.tracks}
    assert programs["melody"] == palette.melody
    assert programs["chords"] == palette.chords
    assert programs["bass"] == palette.bass
    assert programs["drums"] == palette.drums
    assert programs.get("pad") == palette.pad
    assert len(project.tracks) <= 5


def test_lofi_is_rhodes_sub_bass_and_soft_swung_drums(sample):
    project = song(sample, preset="lofi")
    assert project.track("chords").program == 4  # Electric Piano 1, the Rhodes
    assert project.track("bass").program == 38  # Synth Bass 1
    assert project.swing > 0.5
    assert max(n.velocity for n in project.track("drums").notes) < 115


def test_moods_change_the_feel(sample):
    neutral = song(sample, preset="lofi")
    dark, chill, hype = (song(sample, preset="lofi", mood=m) for m in ("dark", "chill", "hype"))
    assert dark.tempo < neutral.tempo < hype.tempo
    assert any(t.role == "pad" for t in dark.tracks)  # dark brings a pad even to lofi
    assert chill.section("verse").intensity < neutral.section("verse").intensity
    assert hype.section("verse").intensity > neutral.section("verse").intensity
    assert dark.track("melody").effects.reverb > neutral.track("melody").effects.reverb


def test_the_pad_stays_out_of_the_verse(sample):
    project = song(sample, preset="cinematic")
    assert notes_in(project, "pad", "chorus") and not notes_in(project, "pad", "verse")


def test_energy_makes_a_section_fuller_or_calmer(sample):
    project = song(sample, energy=(1, -1))
    assert project.section("verse").intensity == 2
    assert project.section("chorus").intensity == 1


def test_genre_words_are_understood():
    assert [preset_for(w).id for w in ("Lo-Fi", "orchestral", "EDM", "jazz", "polka", None)] == [
        "lofi", "cinematic", "electronic", "jazz", "pop", "pop"]


def test_page_settings_become_arrangement_options():
    options = options_from_page({"style": "lofi", "speed": 0.5, "pitch": 1.0, "emotion": 0.1})
    assert (options.preset, options.mood, options.speed, options.transpose) == ("lofi", "dark", 1.0, 12)
    assert options_from_page({"emotion": 0.1, "mood": "hype"}).mood == "hype"  # a chosen mood wins
    assert options_from_page(None).preset == "pop"
    with pytest.raises(ValueError):
        options_from_page({"mood": "furious"})


# ── The project ────────────────────────────────────────────────────────


def test_a_project_survives_its_json_form(sample):
    project = song(sample, preset="jazz", mood="dark")
    data = project.to_json()
    assert Project.from_json(data).to_json() == data


def test_the_project_can_be_arranged_again_from_its_own_phrase(sample):
    project = song(sample, preset="rock")
    again = arrange_phrase(project.phrase, project.hum_tempo, sample.tonic, sample.mode, ArrangeOptions(preset="rock"))
    assert again.to_json() == project.to_json()


@pytest.mark.parametrize(
    "broken",
    [
        {"version": 99},
        {"mode": "dorian"},
        {"tempo": 900},
        {"tracks": [{"id": "a", "role": "melody", "program": 0}, {"id": "a", "role": "bass", "program": 33}]},
        {"tracks": [{"id": "a", "role": "melody", "program": 0, "volume": 3}]},
        {"tracks": [{"id": "a", "role": "kazoo", "program": 0}]},
        {"tracks": [{"id": "a", "role": "melody", "program": 0, "notes": [{"pitch": 300, "start": 0, "duration": 1}]}]},
    ],
)
def test_a_broken_project_is_refused(sample, broken):
    data = {**song(sample).to_json(), **broken}
    with pytest.raises(ValueError):
        Project.from_json(data)
