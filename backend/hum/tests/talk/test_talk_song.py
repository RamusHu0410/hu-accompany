"""How the song settings are translated for the accompanist engine, and how the instruments are
layered on its MIDI. Only the last test renders audio (it needs FluidSynth)."""

import shutil

import pretty_midi
import pytest
from hum.engine.accompanist.music.styles import STYLES
from hum.tests.talk.talk_fakes import write_hum

from hum.engine.talk.settings import DEFAULT_LEAD, PIANO, Part, SongSettings
from hum.engine.talk.song import (
    BACKGROUND_VOLUME,
    ENERGY_STEP,
    ENGINE_STYLE_FOR,
    LEAD_VOLUME,
    LOW,
    OTHER_NAMES,
    PROGRAMS,
    UNKNOWN_STYLE,
    engine_request,
    instrument_name,
    make_song,
    notes_from,
    write_midi,
)

# What analyze_audio_file returns for a hum: MIDI notes with times in seconds, and a tempo
HUM = {"melody": [{"hz": 60.2, "start": 0.0, "duration": 0.5}, {"hz": 64.0, "start": 0.6, "duration": 0.9}], "tempo": 120.0}
# Eight seconds at 120 BPM: four bars, so the song has a first and a second half
TUNE = {"melody": [{"hz": hz, "start": float(n), "duration": 0.9} for n, hz in enumerate([60, 62, 64, 65, 67, 65, 64, 62])], "tempo": 120.0}


def test_middle_settings_keep_the_hum_as_it_was():
    request = engine_request(HUM, SongSettings())
    assert request["tempo"] == 120.0
    # at 120 BPM a beat lasts half a second, so seconds × 2 = beats, snapped to sixteenths (1.2 → 1.25)
    assert request["melody"] == [{"hz": 60.2, "start": 0.0, "duration": 1.0}, {"hz": 64.0, "start": 1.25, "duration": 1.75}]
    assert "style" not in request and "mode" not in request  # the engine's own default style; mode from the hum


@pytest.mark.parametrize(("speed", "tempo"), [(0.0, 60.0), (0.7, 144.0), (1.0, 180.0)])
def test_speed_scales_the_hums_tempo(speed, tempo):
    request = engine_request(HUM, SongSettings(speed=speed))
    assert request["tempo"] == tempo
    assert request["melody"][1]["start"] == 1.25  # the rhythm in beats never changes, only how fast they go


@pytest.mark.parametrize(("pitch", "shift"), [(0.0, -12), (0.4, -2), (0.5, 0), (1.0, 12)])
def test_pitch_moves_the_tune(pitch, shift):
    assert engine_request(HUM, SongSettings(pitch=pitch))["melody"][0]["hz"] == pytest.approx(60.2 + shift)


@pytest.mark.parametrize(("emotion", "mode"), [(0.1, "minor"), (0.39, "minor"), (0.5, None), (0.61, "major")])
def test_emotion_picks_minor_or_major(emotion, mode):
    assert engine_request(HUM, SongSettings(emotion=emotion)).get("mode") == mode


def test_unmeasurable_hum_tempo_falls_back_to_100():
    request = engine_request({**HUM, "tempo": 0.0}, SongSettings())
    assert request["tempo"] == 100.0
    assert request["melody"][1]["start"] == pytest.approx(1.0)  # 0.6 s at 100 BPM


def test_style_words():
    assert engine_request(HUM, SongSettings(style="rock"))["style"] == "pop"
    assert engine_request(HUM, SongSettings(style="polka"))["style"] == UNKNOWN_STYLE


def test_every_word_maps_to_something_the_engine_knows():
    assert set(ENGINE_STYLE_FOR.values()) | {UNKNOWN_STYLE} <= set(STYLES)
    assert set(OTHER_NAMES.values()) | LOW <= set(PROGRAMS)
    assert all(0 <= program <= 127 for program in PROGRAMS.values())


@pytest.mark.parametrize(
    ("word", "name"),
    [("Violins", "violin"), ("saxophone", "sax"), ("horns", "french horn"), ("drum kit", "drums"), ("bass", "bass"), ("kazoo", None), ("", None), ("<b>", None)],
)
def test_instrument_names(word, name):
    assert instrument_name(word) == name


def test_notes_graph_shows_what_was_sung_and_what_plays():
    middle = notes_from(HUM, SongSettings())
    assert middle["sung"] == [{"midi": 60.2, "start": 0.0, "duration": 0.5}, {"midi": 64.0, "start": 0.6, "duration": 0.9}]
    # at the middle settings the song plays the hum as sung, on the sixteenth-note grid
    assert middle["played"] == [{"midi": 60.2, "start": 0.0, "duration": 0.5}, {"midi": 64.0, "start": 0.625, "duration": 0.875}]
    moved = notes_from(HUM, SongSettings(speed=1.0, pitch=0.6))
    assert moved["played"][1] == {"midi": 66.0, "start": 0.417, "duration": 0.583}  # 2 semitones up, 1.5 times as fast
    assert moved["sung"] == middle["sung"]


def test_the_silence_before_the_hum_is_not_part_of_the_tune():
    late = {**HUM, "melody": [{**note, "start": note["start"] + 1.3} for note in HUM["melody"]]}
    assert engine_request(late, SongSettings())["melody"] == engine_request(HUM, SongSettings())["melody"]
    assert notes_from(late, SongSettings())["played"][0]["start"] == 1.3  # drawn where it was hummed


def tracks(tmp_path, settings: SongSettings) -> list[tuple]:
    """The song's MIDI tracks as (program, is_drum, volume, notes); the engine's chords and tune come first."""
    path = str(tmp_path / "song.mid")
    write_midi(path, TUNE, settings, seed="hum.wav")
    return [
        (
            track.program,
            track.is_drum,
            next(change.value for change in track.control_changes if change.number == 7),
            [(note.pitch, round(note.start, 3), round(note.end, 3), note.velocity) for note in track.notes],
        )
        for track in pretty_midi.PrettyMIDI(path).instruments
    ]


def middle_of(song: list[tuple]) -> float:
    return max(note[2] for track in song[:2] for note in track[3]) / 2


def test_the_first_song_is_the_engines_song_on_synth(tmp_path):
    song = tracks(tmp_path, SongSettings())
    # chords and tune on the default synth; the tune's channel is well above the chords'
    assert [track[:3] for track in song] == [(81, False, 85), (81, False, 110)]


@pytest.mark.parametrize("style", [None, "piano", "classical", "jazz"])
def test_the_song_keeps_the_accompanists_tracks_untouched(tmp_path, style):
    """What the app plays is exactly what the accompanist engine renders for the same request."""
    import random

    from hum.engine.accompanist.generate import generate_accompaniment

    settings = SongSettings(style=style)
    request = engine_request(TUNE, settings)
    melody = {"melody": request.pop("melody"), "tempo": request["tempo"]}
    engine_path = str(tmp_path / "engine.mid")
    random.seed("hum.wav")
    generate_accompaniment(melody, engine_path, **request)

    def notes(path):
        return [
            (track.program, [(n.pitch, round(n.start, 4), round(n.end, 4), n.velocity) for n in track.notes])
            for track in pretty_midi.PrettyMIDI(path).instruments
        ]

    app_path = str(tmp_path / "song.mid")
    write_midi(app_path, TUNE, settings, seed="hum.wav")
    assert notes(app_path) == notes(engine_path)


@pytest.mark.parametrize("style", [None, "jazz"])  # jazz plays random fills, so this also checks the seed
def test_adding_instruments_leaves_the_lead_note_for_note(tmp_path, style):
    before = tracks(tmp_path, SongSettings(style=style))
    after = tracks(tmp_path, SongSettings(style=style, instruments=(DEFAULT_LEAD, Part("violin"), Part("cello"), Part("drums"))))
    assert after[:2] == before
    assert len(after) == 5


def test_background_instruments_play_under_the_lead(tmp_path):
    song = tracks(tmp_path, SongSettings(instruments=(PIANO, Part("violin"), Part("cello", level="loud"), Part("drums", level="normal"))))
    violin, cello, drums = song[2:]
    assert violin[:3] == (PROGRAMS["violin"], False, BACKGROUND_VOLUME["soft"])
    assert cello[:3] == (PROGRAMS["cello"], False, BACKGROUND_VOLUME["loud"])
    assert drums[1:3] == (True, BACKGROUND_VOLUME["normal"])
    assert max(BACKGROUND_VOLUME.values()) < LEAD_VOLUME["normal"]  # even a loud background part stays under the lead
    assert max(note[0] for note in cello[3]) < min(note[0] for note in violin[3])  # a bass line under the held chords
    assert {note[0] for note in drums[3]} == {36, 38, 42}  # kick, snare and hi-hat


def test_a_section_limits_where_an_instrument_plays(tmp_path):
    song = tracks(tmp_path, SongSettings(instruments=(PIANO, Part("drums", section="end"), Part("violin", section="start"))))
    drums, violin = song[2:]
    assert drums[3] and all(note[1] >= middle_of(song) for note in drums[3])
    assert violin[3] and all(note[1] < middle_of(song) for note in violin[3])


def test_the_lead_can_be_swapped_and_made_softer(tmp_path):
    song = tracks(tmp_path, SongSettings(instruments=(Part("guitar", "lead", "soft"),)))
    soft = LEAD_VOLUME["soft"] / LEAD_VOLUME["normal"]
    from hum.engine.accompanist.music.accompaniment import ACCOMP_CHANNEL_VOLUME, MELODY_CHANNEL_VOLUME

    # both engine tracks get softer, and the tune stays louder than the chords
    assert [track[:3] for track in song] == [
        (PROGRAMS["guitar"], False, round(ACCOMP_CHANNEL_VOLUME * soft)),
        (PROGRAMS["guitar"], False, round(MELODY_CHANNEL_VOLUME * soft)),
    ]


def test_energy_plays_one_half_harder(tmp_path):
    plain = tracks(tmp_path, SongSettings())
    bigger_ending = tracks(tmp_path, SongSettings(energy=(0, 1)))
    for before, after in zip(plain, bigger_ending):
        for (_, start, _, velocity), (*_, new_velocity) in zip(before[3], after[3]):
            expected = velocity if start < middle_of(plain) else min(127, round(velocity * (1 + ENERGY_STEP)))
            assert new_velocity == expected


def test_instruments_without_a_sound_are_left_out(tmp_path):
    assert len(tracks(tmp_path, SongSettings(instruments=(PIANO, Part("kazoo"))))) == 2


@pytest.mark.skipif(shutil.which("fluidsynth") is None, reason="needs FluidSynth to render audio (brew install fluid-synth)")
def test_a_song_with_background_instruments_renders(tmp_path):
    write_hum(tmp_path / "hum.wav")
    wav = make_song(str(tmp_path / "hum.wav"), SongSettings(instruments=(PIANO, Part("violin"), Part("drums", section="end"))))
    assert wav[:4] == b"RIFF"
