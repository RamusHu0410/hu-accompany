"""Fallbacks (transform -> untransformed melody, effects -> the plain render) and hard failures.

FluidSynth is replaced by a sine tone here (`fake_render`): these are about the plumbing.
"""

import json

import pytest
import soundfile as sf

from hum.engine.audio.arrange import arrange_and_render, steps
from hum.engine.audio.errors import PipelineError
from hum.engine.audio.arrange import effects as fx
from hum.engine.audio.arrange.files import write_atomically
from hum.engine.audio.arrange.config import STYLES
from hum.engine.audio.arrange.melody import load_melody

from conftest import FIXTURE_JSON


def boom(*args, **kwargs):
    raise RuntimeError("boom")


def test_transform_failure_arranges_the_untransformed_melody(tmp_path, fake_render, monkeypatch, melody):
    monkeypatch.setattr(steps, "apply_operations", boom)
    result = arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert result.fell_back is True
    assert any("transformations failed" in w for w in result.warnings)
    arranged = load_melody(tmp_path / "melody_transformed.json")
    intro = STYLES["cinematic"].intro_bars * melody.beats_per_bar
    assert [(n.pitch, n.start_beats - intro) for n in arranged.notes] == [(n.pitch, n.start_beats) for n in melody.notes]
    assert sf.info(result.final_wav_path).subtype == "PCM_24"


def test_effects_failure_returns_the_render_as_24_bit(tmp_path, fake_render, monkeypatch):
    monkeypatch.setattr(fx, "build_chain", boom)
    result = arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert result.fell_back is True
    assert any("effects failed" in w for w in result.warnings)
    final, rendered = sf.info(result.final_wav_path), sf.info(str(tmp_path / "rendered.wav"))
    assert final.subtype == "PCM_24"
    assert final.frames == rendered.frames  # no reverb tail: it's the render itself


def test_no_fallback_when_everything_works(tmp_path, fake_render):
    result = arrange_and_render(str(FIXTURE_JSON), "pop", str(tmp_path))
    assert result.fell_back is False and result.warnings == []


def test_effects_and_its_fallback_both_failing_is_an_error(tmp_path, fake_render, monkeypatch):
    monkeypatch.setattr(fx, "build_chain", boom)
    monkeypatch.setattr(fx, "copy_without_effects", boom)
    with pytest.raises(PipelineError) as caught:
        arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert caught.value.step == "arrange.effects"
    assert not (tmp_path / "final.wav").exists()


def test_orchestration_failure_is_an_error(tmp_path, fake_render, monkeypatch):
    monkeypatch.setattr(steps, "orchestrate", boom)
    with pytest.raises(PipelineError) as caught:
        arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert caught.value.step == "arrange.orchestrate"
    assert not (tmp_path / "arrangement.mid").exists()


def test_missing_soundfont_is_a_render_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDFONT_PATH", str(tmp_path / "nope.sf2"))
    with pytest.raises(PipelineError) as caught:
        arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path / "run"))
    assert caught.value.step == "arrange.render"


def test_an_unknown_style_word_gets_the_default_style_and_a_warning(tmp_path, fake_render):
    result = arrange_and_render(str(FIXTURE_JSON), "polka", str(tmp_path))
    assert result.style == "pop"
    assert result.warnings[0] == "There's no 'polka' style yet, so this was arranged as pop."
    assert result.fell_back is False


@pytest.mark.parametrize("word, style", [("Epic", "cinematic"), ("lo-fi", "modern"), ("lullaby", "piano"),
                                         ("rock", "pop"), ("asian_folk", "classical"), (" Classical ", "classical")])
def test_style_words_map_to_styles(word, style):
    from hum.engine.audio.arrange.config import resolve_style

    assert resolve_style(word) == (style, None)


def test_unusable_melody_json_is_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"tempo_bpm": 92, "key": "D minor", "notes": []}))
    with pytest.raises(PipelineError) as caught:
        arrange_and_render(str(bad), "cinematic", str(tmp_path / "run"))
    assert caught.value.step == "arrange.transform"


def test_a_run_folder_is_never_overwritten(tmp_path, fake_render):
    arrange_and_render(str(FIXTURE_JSON), "pop", str(tmp_path))
    before = (tmp_path / "final.wav").read_bytes()
    with pytest.raises(PipelineError):
        arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert (tmp_path / "final.wav").read_bytes() == before


def test_a_file_that_fails_validation_never_appears(tmp_path):
    def reject(_path):
        raise ValueError("bad")

    with pytest.raises(ValueError):
        write_atomically(tmp_path / "out.txt", lambda tmp: tmp.write_text("x"), reject)
    assert list(tmp_path.iterdir()) == []


def test_atomic_writes_refuse_to_overwrite(tmp_path):
    (tmp_path / "out.txt").write_text("original")
    with pytest.raises(FileExistsError):
        write_atomically(tmp_path / "out.txt", lambda tmp: tmp.write_text("new"))
    assert (tmp_path / "out.txt").read_text() == "original"


@pytest.mark.parametrize("step, error", [("orchestrate", "arranged"), ("render", "sound")])
def test_error_messages_are_written_for_users(tmp_path, fake_render, monkeypatch, step, error):
    """The message is what the app shows; the technical cause is chained for the log."""
    target = {"orchestrate": (steps, "orchestrate"), "render": (steps, "render")}[step]
    monkeypatch.setattr(*target, boom)
    with pytest.raises(PipelineError) as caught:
        arrange_and_render(str(FIXTURE_JSON), "cinematic", str(tmp_path))
    assert error in caught.value.message and "boom" not in caught.value.message
    assert str(caught.value.__cause__) == "boom"


def test_a_long_melody_skips_the_lengthening_without_falling_back(tmp_path, fake_render, melody):
    long = melody.with_notes([n.__class__(n.pitch, n.start_beats + copy * 32, n.duration_beats, n.velocity)
                              for copy in range(3) for n in melody.notes])  # 24 bars; pop would make 48
    path = tmp_path / "long.json"
    from hum.engine.audio.arrange.melody import save_melody_json

    save_melody_json(long, path)
    result = arrange_and_render(str(path), "pop", str(tmp_path / "run"))
    assert result.fell_back is False
    assert any("already 24 bars long" in w for w in result.warnings)


@pytest.mark.parametrize("notes", [[(62, 0.0, 1.5)], [(62, 0, 1), (69, 1, 1), (62, 2, 1), (69, 3, 1)]])
@pytest.mark.parametrize("style", ["piano", "cinematic", "modern", "classical", "pop"])
def test_tiny_melodies_still_get_all_five_tracks(tmp_path, fake_render, melody, notes, style):
    from hum.engine.audio.arrange.melody import Note, save_melody_json

    tiny = melody.with_notes([Note(p, s, d, 80) for p, s, d in notes])
    path = save_melody_json(tiny, tmp_path / "tiny.json")
    result = arrange_and_render(str(path), style, str(tmp_path / "run"))
    assert result.fell_back is False
