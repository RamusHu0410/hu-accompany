"""The pieces between the WAV and the accompanist, each on its own: checking the upload (intake),
the numbers the note finder leans on (notes), the pitch contour the notes graph draws, and the
seconds-to-beats handoff."""

import numpy as np
import pytest
import soundfile as sf

from hum.engine.audio.handoff import DEFAULT_TEMPO, GRID_BEATS, seconds_from_engine, sensible_tempo, to_engine_melody
from hum.engine.audio.intake import AudioInputError, inspect_wav, unique_upload_name
from hum.engine.audio.notes import estimate_tempo_from_onsets, estimate_tuning, noise_gate
from hum.engine.audio.processor import MAX_CONTOUR_POINTS, pitch_contour


# --- intake --------------------------------------------------------------------------------


def _bytes(path, data):
    path.write_bytes(data)
    return str(path)


def _wav(path, seconds, sr=48000, channels=1):
    sf.write(path, np.zeros((int(seconds * sr), channels)) if channels > 1 else np.zeros(int(seconds * sr)), sr)
    return str(path)


def test_a_normal_recording_passes_with_its_facts(tmp_path):
    info = inspect_wav(_wav(tmp_path / "ok.wav", 2.0, channels=2))
    assert info["duration"] == pytest.approx(2.0)
    assert (info["sample_rate"], info["channels"]) == (48000, 2)


@pytest.mark.parametrize(
    ("make", "said"),
    [
        (lambda p: str(p / "missing.wav"), "wasn't found"),
        (lambda p: _bytes(p / "empty.wav", b""), "isn't a readable WAV"),
        (lambda p: _bytes(p / "junk.wav", b"RIFF1234WAVEjunk"), "isn't a readable WAV"),
        (lambda p: _wav(p / "blank.wav", 0.0), "empty"),
        (lambda p: _wav(p / "short.wav", 0.1), "too short"),
        (lambda p: _wav(p / "long.wav", 121, sr=8000), "too long"),
    ],
)
def test_unusable_recordings_say_why(tmp_path, make, said):
    with pytest.raises(AudioInputError, match=said):
        inspect_wav(make(tmp_path))


def test_upload_names_are_safe_and_unique():
    names = {unique_upload_name("recording.wav") for _ in range(50)}
    assert len(names) == 50
    assert all(n.startswith("recording-") and n.endswith(".wav") for n in names)
    assert "/" not in unique_upload_name("../../etc/passwd.wav")


def test_audio_input_error_is_a_value_error():
    """So the talk routes' ValueError handler answers 400 for a bad recording too."""
    assert issubclass(AudioInputError, ValueError)


# --- notes: tempo, tuning, noise gate -----------------------------------------------------


@pytest.mark.parametrize("tempo", [80.0, 100.0, 120.0])
def test_tempo_is_read_from_quarter_and_eighth_note_onsets(tempo):
    beat = 60.0 / tempo
    in_beats = [0, 1, 2, 2.5, 3, 4, 5, 6, 6.5, 7, 8]
    onsets = [b * beat for b in in_beats]
    assert estimate_tempo_from_onsets(onsets) == pytest.approx(tempo, abs=2)


def test_tempo_survives_a_little_human_timing():
    rng = np.random.default_rng(0)
    onsets = np.arange(12) * 0.5 + rng.normal(0, 0.015, 12)  # quarters at 120 BPM, +/-15 ms
    assert estimate_tempo_from_onsets(onsets) == pytest.approx(120, abs=4)


def test_too_few_notes_have_no_tempo():
    assert estimate_tempo_from_onsets([0.0, 0.5]) == 0.0


def test_tuning_of_a_consistently_flat_singer():
    notes = [{"midi": m - 0.3, "duration": 0.4} for m in (60, 62, 64, 65, 67)]
    assert estimate_tuning(notes) == pytest.approx(-0.3, abs=1e-6)


def test_tuning_wraps_around_the_semitone():
    """59.95 and 62.05 are 5 cents either side of C and D: in tune. Averaging their fractional
    parts (0.95 and 0.05) would say a quarter tone off."""
    assert estimate_tuning([{"midi": 59.95, "duration": 1}, {"midi": 62.05, "duration": 1}]) == pytest.approx(0.0, abs=1e-6)


def test_tuning_is_not_guessed_when_the_notes_disagree():
    notes = [{"midi": 60 + offset, "duration": 1} for offset in (0.0, 0.25, 0.5, 0.75)]
    assert estimate_tuning(notes) == 0.0


def test_noise_gate_sits_above_the_noise_floor():
    rms_db = np.concatenate([np.full(50, -40.0), np.full(50, -6.0)])  # noisy room, then a hum
    assert -40 < noise_gate(rms_db) < -6


def test_noise_gate_on_digital_silence_is_relative_to_the_peak():
    rms_db = np.concatenate([np.full(50, -200.0), np.full(50, -6.0)])
    assert noise_gate(rms_db) == pytest.approx(-6 - 45)


# --- handoff: seconds to beats ------------------------------------------------------------


def test_the_first_note_is_beat_zero_and_seconds_become_beats():
    melody = [{"hz": 60.0, "start": 2.0, "duration": 0.5}, {"hz": 62.0, "start": 2.5, "duration": 0.5}]
    assert to_engine_melody(melody, 120.0) == [
        {"hz": 60.0, "start": 0.0, "duration": 1.0},
        {"hz": 62.0, "start": 1.0, "duration": 1.0},
    ]


def test_timing_snaps_to_sixteenths_without_overlaps_or_zero_lengths():
    melody = [
        {"hz": 60.0, "start": 0.0, "duration": 0.33},  # ends past the next start
        {"hz": 62.0, "start": 0.3, "duration": 0.02},  # far shorter than a sixteenth
        {"hz": 64.0, "start": 0.31, "duration": 0.4},  # snaps onto the same step as the note before
    ]
    out = to_engine_melody(melody, 120.0)
    for note in out:
        assert note["start"] % GRID_BEATS == pytest.approx(0) and note["duration"] >= GRID_BEATS
    for a, b in zip(out, out[1:]):
        assert a["start"] + a["duration"] <= b["start"] + 1e-9


def test_no_grid_keeps_the_timing_as_hummed():
    melody = [{"hz": 60.0, "start": 0.0, "duration": 0.33}]
    assert to_engine_melody(melody, 120.0, grid=None)[0]["duration"] == pytest.approx(0.66)


def test_shift_moves_every_note_and_stays_in_midi_range():
    melody = [{"hz": 120.0, "start": 0.0, "duration": 0.5}, {"hz": 5.0, "start": 0.5, "duration": 0.5}]
    assert [n["hz"] for n in to_engine_melody(melody, 120.0, shift=12)] == [127.0, 17.0]


def test_beats_back_to_seconds_on_the_hums_time_axis():
    beats = [{"hz": 60.0, "start": 1.0, "duration": 0.5}]
    assert seconds_from_engine(beats, 120.0, offset=2.0) == [{"hz": 60.0, "start": 2.5, "duration": 0.25}]


@pytest.mark.parametrize(("tempo", "used"), [(None, DEFAULT_TEMPO), (0.0, DEFAULT_TEMPO), (500.0, DEFAULT_TEMPO), (96.0, 96.0)])
def test_only_a_plausible_tempo_is_used(tempo, used):
    assert sensible_tempo(tempo) == used


def test_an_empty_melody_stays_empty():
    assert to_engine_melody([], 120.0) == []


# --- the pitch contour the notes graph draws -------------------------------------------------


def _pitch(hz, voiced, rms_db=None, step=0.01):
    """A pYIN-shaped track: one frame per entry, ``step`` seconds apart."""
    return {
        "times": [i * step for i in range(len(hz))],
        "frequencies": list(hz),
        "voiced_flag": list(voiced),
        "rms_db": list(rms_db if rms_db is not None else [-10.0] * len(hz)),
    }


def test_a_silence_breaks_the_line_into_two_phrases():
    hz = [220.0] * 20 + [0.0] * 20 + [330.0] * 20
    voiced = [True] * 20 + [False] * 20 + [True] * 20
    contour = pitch_contour(_pitch(hz, voiced))
    assert len(contour["segments"]) == 2
    assert contour["segments"][1]["start"] == pytest.approx(0.4)


def test_the_contour_keeps_the_pitch_as_it_was_sung():
    """A scoop up into a note stays a slide, where segment_notes would flatten it to one pitch."""
    hz = [220.0 * 2 ** (i / 39 / 12) for i in range(40)]  # a semitone, slid over 40 frames
    contour = pitch_contour(_pitch(hz, [True] * 40))
    sung = contour["segments"][0]["midi"]
    assert sung == sorted(sung)  # it rises all the way, never rounded into a step
    assert sung[-1] - sung[0] == pytest.approx(1.0, abs=0.05)


def test_tuning_is_corrected_like_the_notes():
    flat = pitch_contour(_pitch([220.0] * 20, [True] * 20), tuning=-0.5)
    assert flat["segments"][0]["midi"][0] == pytest.approx(57.5, abs=0.01)


def test_loudness_becomes_a_level_between_the_gate_and_the_loudest_frame():
    quiet_to_loud = [-60.0] * 10 + list(range(-40, 0, 4))
    contour = pitch_contour(_pitch([220.0] * 20, [True] * 20, quiet_to_loud))
    levels = [l for segment in contour["segments"] for l in segment["level"]]
    assert min(levels) >= 0.0 and max(levels) == pytest.approx(1.0)


def test_a_long_hum_is_thinned_to_a_sendable_size():
    frames = MAX_CONTOUR_POINTS * 3
    contour = pitch_contour(_pitch([220.0] * frames, [True] * frames))
    assert sum(len(s["midi"]) for s in contour["segments"]) <= MAX_CONTOUR_POINTS
    assert contour["step"] == pytest.approx(0.03)  # three frames became one


@pytest.mark.parametrize("pitch", [None, {}, _pitch([220.0], [True])])
def test_nothing_to_draw_is_an_empty_contour(pitch):
    assert pitch_contour(pitch)["segments"] == []
