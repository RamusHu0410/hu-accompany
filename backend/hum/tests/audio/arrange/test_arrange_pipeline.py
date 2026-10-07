"""pipeline.py: a run folder with every step's files and a log, and re-runs from saved steps."""

import hashlib
import json

import pytest

from hum.engine.audio import pipeline
from hum.engine.audio.errors import PipelineError

from conftest import FIXTURE_JSON, FIXTURE_MIDI


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


@pytest.fixture
def upload(tmp_path):
    """Stands in for the user's upload (the fixture intake ignores its contents)."""
    path = tmp_path / "hum.wav"
    path.write_bytes(b"RIFF....WAVE")
    return path


def test_a_run_keeps_every_step_and_logs_it(runs, upload, fake_render):
    result = pipeline.run_pipeline(str(upload), "cinematic", intake="fixture")
    run_dir = runs / result.run_id
    assert result.run_dir == str(run_dir)
    for name in ("melody_clean.mid", "melody.json", "melody_transformed.json", "melody_transformed.mid",
                 "arrangement.mid", "rendered.wav", "final.wav", "run.json"):
        assert (run_dir / name).is_file(), name
    assert not (run_dir / "hum.wav").exists()  # the raw hum is never stored

    log = json.loads((run_dir / "run.json").read_text())
    assert log["status"] == "ok"
    assert [s["step"] for s in log["steps"]] == ["intake", "transform", "orchestrate", "render", "effects"]
    assert all(s["status"] == "ok" for s in log["steps"])
    assert log["input"]["sha256"] == digest(upload)
    assert log["final"] == "final.wav" and log["style"] == "cinematic" and log["intake"] == "fixture"
    assert any("fixture melody" in w for w in result.warnings)


def test_the_stub_hands_over_the_fixture(runs, upload, fake_render):
    result = pipeline.run_pipeline(str(upload), "pop", intake="fixture")
    assert result.melody.note_count == 28
    assert digest(runs / result.run_id / "melody.json") == digest(FIXTURE_JSON)
    assert digest(runs / result.run_id / "melody_clean.mid") == digest(FIXTURE_MIDI)


def test_rerun_with_a_new_style_from_the_saved_melody(runs, upload, fake_render):
    first = pipeline.run_pipeline(str(upload), "cinematic", intake="fixture")
    source = runs / first.run_id
    before = {p.name: digest(p) for p in source.iterdir()}

    again = pipeline.rerun(source, "pop", from_step="transform")
    new = runs / again.run_id
    assert new != source
    assert {p.name: digest(p) for p in source.iterdir()} == before  # the saved run is untouched
    assert digest(new / "melody.json") == before["melody.json"]
    assert digest(new / "melody_transformed.json") != before["melody_transformed.json"]  # pop repeats the tune

    log = json.loads((new / "run.json").read_text())
    assert log["parent_run"] == str(source) and log["start_step"] == "transform" and log["style"] == "pop"
    assert [s["step"] for s in log["steps"]] == ["reuse", "transform", "orchestrate", "render", "effects"]


def test_rerun_only_the_effects(runs, upload, fake_render):
    first = pipeline.run_pipeline(str(upload), "cinematic", intake="fixture")
    source = runs / first.run_id
    again = pipeline.rerun(source, "piano", from_step="effects")
    new = runs / again.run_id
    for name in ("arrangement.mid", "rendered.wav"):
        assert digest(new / name) == digest(source / name), name
    log = json.loads((new / "run.json").read_text())
    assert [s["step"] for s in log["steps"]] == ["reuse", "effects"]


def test_rerun_needs_the_saved_input(runs, tmp_path):
    empty = tmp_path / "old_run"
    empty.mkdir()
    with pytest.raises(PipelineError, match="melody.json"):
        pipeline.rerun(empty, "pop", from_step="transform")


def test_rerun_from_an_unknown_step_is_refused(runs, tmp_path):
    with pytest.raises(PipelineError, match="choose one of"):
        pipeline.rerun(tmp_path, "pop", from_step="mastering")


def test_a_run_folder_must_start_empty(tmp_path, upload):
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "something").write_text("x")
    with pytest.raises(PipelineError) as caught:
        pipeline.run_pipeline(str(upload), "pop", run_dir=str(tmp_path / "busy"), intake="fixture")
    assert caught.value.step == "pipeline.setup"


def test_intake_failure_is_logged(runs, upload):
    def transcribe(input_path, run_dir):
        raise RuntimeError("no pitch found")

    with pytest.raises(PipelineError) as caught:
        pipeline.run_pipeline(str(upload), "pop", intake=transcribe)
    assert caught.value.step == "intake"
    run_dir = next(runs.iterdir())
    log = json.loads((run_dir / "run.json").read_text())
    assert log["status"] == "failed"
    assert log["steps"][-1] == {**log["steps"][-1], "step": "intake", "status": "failed"}
    assert log["error"] == "intake: Your recording couldn't be turned into notes."
    assert "no pitch found" in log["detail"]  # the technical cause, for whoever debugs it


def test_a_handoff_with_disagreeing_files_warns(runs, upload, fake_render):
    """melody.json wins when the MIDI disagrees with it (the contract's source of truth)."""
    import pretty_midi

    real = pipeline._fixture_transcribe

    def short_midi_intake(input_path, run_dir):
        result = real(input_path, run_dir)
        midi = pretty_midi.PrettyMIDI(result.midi_path)
        midi.instruments[0].notes = midi.instruments[0].notes[:5]
        midi.write(result.midi_path)
        return result

    result = pipeline.run_pipeline(str(upload), "pop", intake=short_midi_intake)
    assert any("has 5 notes but melody.json has 28" in w for w in result.warnings)


def test_intake_is_chosen_by_name_or_environment(monkeypatch):
    from hum.engine.audio.intake import transcribe_to_melody

    monkeypatch.delenv("PIPELINE_INTAKE", raising=False)
    assert pipeline.get_intake() is transcribe_to_melody  # part A's, by default
    assert pipeline.get_intake("fixture") is pipeline._fixture_transcribe
    monkeypatch.setenv("PIPELINE_INTAKE", "fixture")
    assert pipeline.get_intake() is pipeline._fixture_transcribe
    with pytest.raises(PipelineError) as caught:
        pipeline.get_intake("guess")
    assert caught.value.code == "unknown_intake"
