"""The whole intake on tests/fixtures/hum_sample.wav, whose right answer is known (hum_synth.HUM_SAMPLE)."""

import json
import os
import stat

import pytest

from hum.engine.audio.intake import transcribe_to_melody
from hum.engine.audio.intake.normalize import sha256_of
from hum.engine.audio.intake.output import check_pair

from .hum_synth import FIXTURE, HUM_SAMPLE, HUM_SAMPLE_TEMPO, HUM_SAMPLE_TUNING_CENTS

D3, F3 = 50, 53


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("run")
    before = sha256_of(FIXTURE)
    result = transcribe_to_melody(str(FIXTURE), str(run_dir))
    with open(result.json_path) as file:
        melody = json.load(file)
    with open(run_dir / "intake_log.json") as file:
        log = json.load(file)
    return result, melody, log, run_dir, before


def test_the_melody_is_exactly_what_was_hummed(run):
    result, melody, _, _, _ = run
    heard = [(n["pitch"], n["start_beats"], n["duration_beats"]) for n in melody["notes"]]
    hummed = [(n.pitch, pytest.approx(n.start, abs=1e-3), pytest.approx(n.beats, abs=1e-3)) for n in HUM_SAMPLE]
    assert heard == hummed
    assert result.note_count == len(HUM_SAMPLE) and not result.fell_back


def test_a_sane_melody_in_range_with_no_ghosts_or_fragments(run):
    _, melody, _, _, _ = run
    notes = melody["notes"]
    assert 5 <= len(notes) <= 20
    assert all(D3 <= n["pitch"] <= F3 for n in notes)  # no octave outliers
    seconds_per_beat = 60 / melody["tempo_bpm"]
    assert all(n["duration_beats"] * seconds_per_beat >= 0.08 for n in notes)  # no fragments under 80 ms
    assert all(a["start_beats"] + a["duration_beats"] <= b["start_beats"] + 1e-9 for a, b in zip(notes, notes[1:]))  # one at a time


def test_tempo_key_and_tuning_are_detected(run):
    _, melody, _, _, _ = run
    assert melody["tempo_bpm"] == pytest.approx(HUM_SAMPLE_TEMPO, abs=1.0)
    assert melody["key"] == "D minor"
    assert melody["time_signature"] == "4/4"
    assert abs(melody["tuning_offset_cents"] - HUM_SAMPLE_TUNING_CENTS) <= 5


def test_the_files_follow_the_contract(run):
    result, melody, _, run_dir, _ = run
    assert os.path.basename(result.midi_path) == "melody_clean.mid"
    assert os.path.basename(result.json_path) == "melody.json"
    assert set(melody) == {"tempo_bpm", "key", "time_signature", "tuning_offset_cents", "notes"}
    assert all(set(n) == {"pitch", "start_beats", "duration_beats", "velocity"} for n in melody["notes"])
    assert all(1 <= n["velocity"] <= 127 for n in melody["notes"])
    check_pair(result.midi_path, result.json_path)  # the MIDI is one program-0 track with the same notes and key
    assert sorted(os.listdir(run_dir)) == ["intake_log.json", "intake_normalized.wav", "intake_original.wav", "melody.json", "melody_clean.mid"]
    assert not [name for name in os.listdir(run_dir) if name.endswith(".tmp")]


def test_the_original_is_kept_read_only_and_never_changed(run):
    _, _, log, run_dir, before = run
    copy = run_dir / "intake_original.wav"
    assert not os.stat(copy).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert sha256_of(copy) == before == log["original"]["sha256"]
    assert sha256_of(FIXTURE) == before


def test_the_log_counts_the_notes_before_and_after_cleanup(run):
    _, _, log, _, _ = run
    assert set(log["notes"]) == {"raw", "lightly_filtered", "clean"}
    assert log["notes"]["clean"] == len(HUM_SAMPLE)
    assert log["notes"]["raw"] >= log["notes"]["clean"]
    assert "error" not in log


def test_the_committed_fixture_is_what_the_intake_makes_today(run):
    """tests/fixtures/hum_sample.melody.json is step B's test input. If the intake changes what it
    makes, regenerate it (and the .mid beside it) so B tests against real output."""
    _, melody, _, _, _ = run
    with open(FIXTURE.with_name("hum_sample.melody.json")) as file:
        committed = json.load(file)
    assert committed["notes"] == melody["notes"]
    assert (committed["key"], committed["time_signature"]) == (melody["key"], melody["time_signature"])
    assert committed["tempo_bpm"] == pytest.approx(melody["tempo_bpm"], abs=0.5)
