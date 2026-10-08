"""The multi-track arrangement: the right tracks and programs, in range and in key, shaped by phrase."""

import pytest
from music21 import converter

from hum.engine.audio.arrange import orchestrate as O
from hum.engine.audio.arrange.config import CONCERT_BASS_DRUM, CRASH, INSTRUMENT_RANGES, STYLES
from hum.engine.audio.arrange.melody import key_pitch_classes
from hum.engine.audio.arrange.transforms import fit_pitches
from hum.engine.audio.arrange.validate import validate_midi

D_MINOR = key_pitch_classes("D minor")


def arrange(melody, style="cinematic"):
    midi, warnings = O.orchestrate(melody, STYLES[style].orchestration)
    return {inst.name: inst for inst in midi.instruments}, midi, warnings


def bars_at(seconds, melody):
    return seconds / (melody.beats_per_bar * melody.seconds_per_beat)


def test_phrases_and_their_peaks(melody):
    assert O.find_phrases(melody) == [O.Phrase(0, 4, 1), O.Phrase(4, 8, 4)]  # the Bb, then the D5


@pytest.mark.parametrize("style", sorted(STYLES))
def test_every_track_with_the_style_programs(melody, style):
    tracks, midi, warnings = arrange(melody, style)
    preset = STYLES[style].orchestration
    names = O.track_names(preset)
    assert [i.name for i in midi.instruments] == names
    assert ("timpani" in names) == preset.timpani
    programs = {"melody": preset.lead, "melody_double": preset.double, "strings_pad": preset.pad,
                "figure": preset.figure, "bass": preset.bass, "brass": preset.brass}
    assert {name: tracks[name].program for name in programs} == programs
    assert tracks["percussion"].is_drum and not any(tracks[n].is_drum for n in names[:-1])
    assert all(tracks[n].notes for n in names)  # every instrument plays
    assert warnings == []


@pytest.mark.parametrize("style", sorted(STYLES))
def test_every_pitched_note_is_in_its_instruments_range(melody, style):
    tracks, _, _ = arrange(melody, style)
    for name in O.track_names(STYLES[style].orchestration)[:-1]:
        low, high = INSTRUMENT_RANGES[tracks[name].program]
        assert all(low <= n.pitch <= high for n in tracks[name].notes), name


def test_melody_is_the_tune_moved_into_the_leads_range(melody):
    tracks, _, _ = arrange(melody)
    expected = fit_pitches([n.pitch for n in melody.notes], *INSTRUMENT_RANGES[STYLES["cinematic"].orchestration.lead])
    assert [n.pitch for n in tracks["melody"].notes] == expected
    spb = melody.seconds_per_beat
    assert [round(n.start / spb, 6) for n in tracks["melody"].notes] == [n.start_beats for n in melody.notes]


@pytest.mark.parametrize("style", sorted(STYLES))
def test_harmony_stays_in_key_for_every_styles_transformed_melody(melody, style):
    from hum.engine.audio.arrange.transforms import apply_operations

    tracks, _, _ = arrange(apply_operations(melody, STYLES[style].transforms), style)
    for name in ("strings_pad", "figure", "bass", "brass", "timpani"):
        if name in tracks:
            assert {n.pitch % 12 for n in tracks[name].notes} <= D_MINOR, name


def test_an_out_of_key_chord_is_replaced_by_the_best_fitting_one_in_key(melody):
    e_minor = O.ChordSpan(24.0, 4.0, (4, 7, 11))  # bar 7: G Bb A E in the melody
    fixed = O._in_key(e_minor, melody)
    assert set(fixed.pitch_classes) <= D_MINOR
    assert (fixed.start_beats, fixed.duration_beats) == (24.0, 4.0)
    assert fixed.pitch_classes in O.diatonic_triads("D minor")


def test_phrases_restart_at_each_section(melody):
    from hum.engine.audio.arrange.transforms import apply_operations

    built = apply_operations(melody, [("additive", {})])  # a 3-bar build-up, then the 8-bar tune
    assert [(p.start_bar, p.end_bar) for p in O.find_phrases(built)] == [(0, 3), (3, 7), (7, 11)]


def test_hits_land_on_downbeats_including_every_peak(melody):
    tracks, _, _ = arrange(melody)
    hits = [n for n in tracks["percussion"].notes if n.pitch in (CONCERT_BASS_DRUM, CRASH)]
    positions = [bars_at(n.start, melody) for n in hits]
    assert all(abs(p - round(p)) < 1e-6 for p in positions)
    crashes = {round(bars_at(n.start, melody)) for n in hits if n.pitch == CRASH}
    assert crashes == {1, 4, 7}  # both phrase peaks and the final bar


def test_brass_swells_rise_into_each_peak(melody):
    tracks, _, _ = arrange(melody)
    swells = [cc for cc in tracks["brass"].control_changes if cc.number == 11]
    bar = melody.beats_per_bar * melody.seconds_per_beat
    for peak in (1, 4, 7):
        ramp = [cc.value for cc in swells if (peak - 1) * bar - 1e-6 <= cc.time < peak * bar - 1e-6]
        assert ramp == sorted(ramp) and ramp[0] < 50 and ramp[-1] == 127, peak
        arrivals = [n for n in tracks["brass"].notes if abs(n.start - peak * bar) < 1e-6]
        assert arrivals, f"no brass chord on the downbeat of bar {peak}"


def test_dynamics_build_toward_the_peak(melody):
    tracks, _, _ = arrange(melody)
    pad = sorted(tracks["strings_pad"].notes, key=lambda n: n.start)
    bar = melody.beats_per_bar * melody.seconds_per_beat
    velocity_at = {round(n.start / bar): n.velocity for n in pad if abs(n.start / bar - round(n.start / bar)) < 1e-6}
    assert velocity_at[0] < velocity_at[1]  # into the first peak
    assert velocity_at[4] > velocity_at[7]  # easing off after the second


def test_written_arrangement_reads_in_music21_and_pretty_midi(melody, tmp_path):
    _, midi, _ = arrange(melody)
    path = tmp_path / "arrangement.mid"
    midi.write(str(path))
    validate_midi(path, min_tracks=len(O.TRACKS), music21=True)
    assert len(converter.parse(str(path)).parts) == len(O.track_names(STYLES["cinematic"].orchestration))


def test_harmony_falls_back_to_the_tonic_if_the_accompanist_fails(melody, monkeypatch):
    import hum.engine.accompanist.music.progression as progression

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    from hum.engine.audio.arrange import config

    monkeypatch.setattr(config, "HARMONY", "accompanist")
    monkeypatch.setattr(progression, "generate_progression", broken)
    chords, warnings = O.harmonize(melody)
    assert warnings and "tonic" in warnings[0]
    assert {c.pitch_classes for c in chords} == {(2, 5, 9)}  # D minor triad


def test_diatonic_triads_start_on_the_tonic():
    """music21 lists a minor scale from its relative major; the chords must start on the tonic."""
    from hum.engine.audio.arrange.debug import chord_name

    assert [chord_name(t) for t in O.diatonic_triads("D minor")] == ["Dm", "Edim", "F", "Gm", "Am", "Bb", "C"]
    assert [chord_name(t) for t in O.diatonic_triads("C major")] == ["C", "Dm", "Em", "F", "G", "Am", "Bdim"]


def test_builtin_harmony_opens_on_the_tonic_and_closes_with_a_cadence(melody):
    chords = O.builtin_progression(melody)
    assert chords[0].pitch_classes == (2, 5, 9)  # Dm
    assert chords[-1].pitch_classes == (2, 5, 9)
    assert chords[-2].root in (7, 9)  # iv or v before it
    assert sum(c.duration_beats for c in chords) == melody.bars * melody.beats_per_bar


def test_builtin_harmony_is_fast_on_a_long_melody(melody):
    import time

    long = melody.with_notes([n.__class__(n.pitch, n.start_beats + k * 32, n.duration_beats, n.velocity)
                              for k in range(12) for n in melody.notes])  # 96 bars
    began = time.monotonic()
    O.builtin_progression(long)
    assert time.monotonic() - began < 1.0


def test_the_accompanist_engine_is_still_an_option(melody, monkeypatch):
    from hum.engine.audio.arrange import config

    monkeypatch.setattr(config, "HARMONY", "accompanist")
    chords, warnings = O.harmonize(melody)
    assert warnings == [] and all(set(c.pitch_classes) <= D_MINOR for c in chords)


@pytest.mark.parametrize("style", sorted(STYLES))
def test_the_figure_keeps_moving(melody, style):
    """The accompaniment isn't just held chords: several notes in every bar."""
    tracks, _, _ = arrange(melody, style)
    bar = melody.beats_per_bar * melody.seconds_per_beat
    per_bar = [sum(1 for n in tracks["figure"].notes if b * bar <= n.start < (b + 1) * bar) for b in range(melody.bars)]
    assert min(per_bar) >= 2, per_bar


def test_the_doubling_joins_for_the_second_part(melody):
    """It builds: the lead alone first, a second instrument on the tune from the second phrase."""
    tracks, _, _ = arrange(melody)
    second_phrase = 4 * melody.beats_per_bar * melody.seconds_per_beat
    starts = [n.start for n in tracks["melody_double"].notes]
    assert starts and min(starts) >= second_phrase - 1e-6
    assert len(starts) == sum(1 for n in melody.notes if n.start_beats >= 16)


def test_a_pad_lead_is_doubled_from_the_start(melody):
    from hum.engine.audio.arrange import ArrangeSettings

    midi, _ = O.orchestrate(melody, STYLES["cinematic"].orchestration, ArrangeSettings(lead=89))  # the page's synth pad
    double = next(i for i in midi.instruments if i.name == "melody_double")
    assert len(double.notes) == len(melody.notes) and double.notes[0].start == 0


def test_timpani_roll_into_each_peak(melody):
    tracks, _, _ = arrange(melody)
    bar = melody.beats_per_bar * melody.seconds_per_beat
    beat = melody.seconds_per_beat
    for peak in (1, 4, 7):
        roll = [n for n in tracks["timpani"].notes if peak * bar - beat - 1e-6 <= n.start < peak * bar - 1e-6]
        assert len(roll) == 8 and [n.velocity for n in roll] == sorted(n.velocity for n in roll), peak


@pytest.mark.parametrize("style", sorted(STYLES))
def test_several_instruments_play_at_once_all_through(melody, style):
    """Never a lone instrument: in every bar at least four tracks are sounding."""
    tracks, midi, _ = arrange(melody, style)
    bar = melody.beats_per_bar * melody.seconds_per_beat
    for b in range(melody.bars):
        playing = {i.name for i in midi.instruments for n in i.notes if n.start < (b + 1) * bar and n.end > b * bar}
        assert len(playing) >= 4, (b, playing)

