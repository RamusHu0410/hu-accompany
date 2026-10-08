"""Every intake must meet the pipeline contract: part A's transcribe_to_melody (app/audio/intake)
and the fixture stand-in are run on a hum, and what they hand over is checked before the
arrangement takes it."""

import hashlib

import pretty_midi
import pytest

from hum.engine.audio import pipeline
from hum.engine.audio.arrange import arrange_and_render
from hum.engine.audio.arrange.demo import synthesize_hum
from hum.engine.audio.arrange.melody import load_melody


def _intakes():
    return [("fixture", pipeline._fixture_transcribe), ("intake", pipeline.INTAKES["intake"])]


@pytest.fixture(scope="module")
def hum(tmp_path_factory):
    from conftest import FIXTURE_JSON

    return synthesize_hum(load_melody(FIXTURE_JSON), tmp_path_factory.mktemp("hum") / "hum_sample.wav")


@pytest.mark.parametrize("name, transcribe", _intakes())
def test_intake_meets_the_contract(name, transcribe, hum, tmp_path, fake_render):
    before = hashlib.sha256(hum.read_bytes()).hexdigest()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = transcribe(str(hum), str(run_dir))

    # MelodyResult: midi_path, json_path, note_count, fell_back, warnings
    assert result.json_path == str(run_dir / "melody.json")
    assert result.midi_path == str(run_dir / "melody_clean.mid")
    assert isinstance(result.fell_back, bool) and isinstance(result.warnings, list)

    melody = load_melody(result.json_path)  # the contract's JSON, validated
    assert result.note_count == len(melody.notes) > 0

    midi = pretty_midi.PrettyMIDI(result.midi_path)
    assert len(midi.instruments) == 1 and midi.instruments[0].program == 0  # one instrument, program 0
    midi_notes = sorted(midi.instruments[0].notes, key=lambda n: n.start)
    assert [n.pitch for n in midi_notes] == [n.pitch for n in melody.notes]  # the same notes
    assert all(a.end_beats <= b.start_beats + 1e-6 for a, b in zip(melody.notes, melody.notes[1:]))  # monophonic
    assert all(abs(n.start_beats * 48 - round(n.start_beats * 48)) < 1e-6 for n in melody.notes)  # quantized

    assert hashlib.sha256(hum.read_bytes()).hexdigest() == before  # the upload is never changed
    assert arrange_and_render(result.json_path, "piano", str(run_dir)).final_wav_path  # B accepts it
