"""The debug tools: the run report and per-track stems."""

import soundfile as sf

from hum.engine.audio import pipeline
from hum.engine.audio.arrange import debug


def test_describe_reports_every_step(tmp_path, fake_render):
    result = pipeline.run_pipeline(str(tmp_path / "hum.wav"), "modern", run_dir=str(tmp_path / "run"), intake="fixture")
    report = debug.describe(result.run_dir)
    for expected in ("status ok", "intake fixture", "transform", "orchestrate", "render", "effects",
                     "melody.json: 28 notes, 8 bars, D minor", "sections start at bar 1, 4",
                     "phrases (bars, peak):  1-3", "harmony (beat:chord): 0:", "Vibraphone", "final.wav", "PCM_24"):
        assert expected in report, expected


def test_describe_says_when_the_transform_was_copied(tmp_path, fake_render):
    first = pipeline.run_pipeline(str(tmp_path / "hum.wav"), "cinematic", run_dir=str(tmp_path / "a"), intake="fixture")
    again = pipeline.rerun(first.run_dir, "piano", from_step="effects", run_dir=str(tmp_path / "b"))
    assert "copied from the parent run" in debug.describe(again.run_dir)


def test_chord_names():
    assert [debug.chord_name(c) for c in [(2, 5, 9), (10, 2, 5), (4, 7, 10), (0, 4, 8)]] == ["Dm", "Bb", "Edim", "Caug"]


def test_stems_render_each_track_alone(tmp_path, fake_render, soundfont):
    result = pipeline.run_pipeline(str(tmp_path / "hum.wav"), "piano", run_dir=str(tmp_path / "run"), intake="fixture")
    stems = debug.render_stems(result.run_dir, soundfont)
    from hum.engine.audio.arrange.config import STYLES
    from hum.engine.audio.arrange.orchestrate import track_names

    assert sorted(p.name for p in stems) == sorted(f"stem_{t}.wav" for t in track_names(STYLES["piano"].orchestration))
    assert all(sf.info(str(p)).frames > 0 for p in stems)
    assert debug.render_stems(result.run_dir, soundfont) == stems  # a second call leaves them as they are
