"""A hum as notes (hum/transcription.py) and played back as hummed (hum/rawplay.py).

The hums are made by tests/audio/intake/hum_synth.py, whose right answers are known. Plain pytest
(no Django); run with `python -m pytest hum/tests/test_transcription.py`.
"""

import io
import shutil
from pathlib import Path

import mido
import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from hum import rawplay
from hum.engine.accompanist.audio.render import find_soundfont
from hum.engine.audio.errors import PipelineError
from hum.tests.audio.intake.hum_synth import HUM_SAMPLE, HUM_SAMPLE_TEMPO, Sung, hum, write
from hum.transcription import (
    HeardNote,
    Transcription,
    snap_to_scale,
    tonic_pitch_class,
    transcribe_hum,
    transcription_for,
)

SAMPLE = Path(__file__).parent / "fixtures" / "hum_sample.wav"
BEAT = 60 / HUM_SAMPLE_TEMPO


def can_render() -> bool:
    try:
        find_soundfont()
    except FileNotFoundError:
        return False
    return shutil.which("fluidsynth") is not None


@pytest.fixture(scope="module")
def sample() -> Transcription:
    return transcribe_hum(SAMPLE)


def hummed(tmp_path, notes, tempo=100.0, **options) -> Transcription:
    return transcribe_hum(write(tmp_path / "hum.wav", hum(notes, tempo=tempo, **options)))


# ── Transcription ──────────────────────────────────────────────────────


def test_every_note_of_a_real_hum_is_found_at_the_pitch_that_was_sung(sample):
    assert [n.pitch for n in sample.raw] == [n.pitch for n in HUM_SAMPLE]


def test_onsets_and_lengths_follow_the_singer_not_a_grid(sample):
    first = HUM_SAMPLE[0].start * BEAT
    for heard, sung in zip(sample.raw, HUM_SAMPLE):
        assert heard.start == pytest.approx(sung.start * BEAT - first, abs=0.08)
        assert heard.duration == pytest.approx(sung.beats * BEAT, abs=0.12)


def test_the_first_note_starts_at_zero(sample):
    assert sample.raw[0].start == 0


def test_tempo_key_and_tuning_are_found(sample):
    assert sample.tempo_bpm == pytest.approx(HUM_SAMPLE_TEMPO, rel=0.03)
    assert (sample.tonic, sample.mode) == ("D", "minor")
    assert sample.tuning_cents == pytest.approx(14, abs=6)  # the hum was sung 14 cents sharp
    assert not sample.fell_back


def test_loudness_comes_through_as_velocity(sample):
    assert all(1 <= n.velocity <= 127 for n in sample.raw)


def test_vibrato_on_a_held_note_is_still_one_note(tmp_path):
    result = hummed(tmp_path, [Sung(57, 0, 1), Sung(60, 1, 3, "legato", vibrato=True)], vibrato_semitones=0.5)
    assert [n.pitch for n in result.raw] == [57, 60]


def test_glides_into_notes_do_not_add_notes(tmp_path):
    result = hummed(tmp_path, [Sung(55, 0, 1, scoop=True), Sung(57, 1, 1, "legato", scoop=True), Sung(59, 2, 2, "legato")])
    assert [n.pitch for n in result.raw] == [55, 57, 59]


def test_a_silence_between_phrases_stays_a_silence(tmp_path):
    result = hummed(tmp_path, [Sung(60, 0, 1), Sung(62, 1, 1, "legato"), Sung(64, 4, 1), Sung(65, 5, 1, "legato")], tempo=120)
    gap = result.raw[2].start - result.raw[1].end
    assert gap == pytest.approx(1.0, abs=0.15)  # two beats at 120 bpm, less the note before it


def test_a_hum_in_the_chest_register_is_not_lifted_an_octave(tmp_path):
    low = hummed(tmp_path, [Sung(43, 0, 1), Sung(45, 1, 1, "legato"), Sung(47, 2, 2, "legato")])
    assert [n.pitch for n in low.raw] == [43, 45, 47]


def test_silence_is_refused_with_a_reason(tmp_path):
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros(44100 * 2, dtype="float32"), 44100)
    with pytest.raises(PipelineError) as refused:
        transcribe_hum(path)
    assert refused.value.code == "silent"


def test_breath_noise_alone_is_not_a_tune(tmp_path):
    noise = (np.random.default_rng(3).normal(0, 0.02, 44100 * 2)).astype("float32")
    path = tmp_path / "breath.wav"
    sf.write(path, noise, 44100)
    with pytest.raises(PipelineError) as refused:
        transcribe_hum(path)
    assert refused.value.code in {"no_tune", "silent", "too_short"}


def test_a_transcription_is_saved_and_read_back(tmp_path, sample):
    cache = tmp_path / "cache"
    first = transcription_for(SAMPLE, cache)
    assert (cache / "hum_sample.json").is_file()
    again = transcription_for(SAMPLE, cache)  # served from the saved copy
    assert again.raw == first.raw == sample.raw
    assert (again.tonic, again.mode, again.tempo_bpm) == (first.tonic, first.mode, first.tempo_bpm)


def test_a_saved_copy_from_another_version_is_heard_again(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "hum_sample.json").write_text('{"version": 0}')
    assert len(transcription_for(SAMPLE, cache).raw) == len(HUM_SAMPLE)


# ── Raw versus quantized ───────────────────────────────────────────────


def test_quantizing_moves_notes_onto_the_grid_and_leaves_the_raw_notes_alone(sample):
    before = list(sample.raw)
    grid = sample.quantized()

    assert sample.raw == before
    assert len(grid) == len(sample.raw)
    for note in grid:
        in_sixteenths = abs(note.start * 4 - round(note.start * 4)) < 1e-4
        in_triplets = abs(note.start * 3 - round(note.start * 3)) < 1e-4
        assert in_sixteenths or in_triplets
    assert any(abs(n.start - round(n.start * 4) / 4) > 0.01 for n in _in_beats(sample))  # the raw ones are not


def _in_beats(transcription):
    per_second = transcription.tempo_bpm / 60
    return [HeardNote(n.pitch, n.start * per_second, n.duration * per_second, n.velocity) for n in transcription.raw]


def test_quantized_notes_never_overlap(sample):
    grid = sample.quantized()
    for a, b in zip(grid, grid[1:]):
        assert a.start + a.duration <= b.start + 1e-6


def test_every_quantized_note_is_in_the_key():
    heard = [HeardNote(61, 0.0, 0.5, 90), HeardNote(66, 0.5, 0.5, 90), HeardNote(70, 1.0, 0.5, 90)]
    result = Transcription(heard, 120.0, "C", "major")

    assert [n.pitch for n in result.quantized()] == [60, 65, 69]  # C# -> C, F# -> F, Bb -> A
    assert [n.pitch for n in result.raw] == [61, 66, 70]


@pytest.mark.parametrize(
    ("pitch", "tonic", "mode", "expected"),
    [
        (60, 0, "major", 60),  # already in the key
        (61, 0, "major", 60),  # a tie goes down
        (66, 0, "major", 65),
        (63, 0, "minor", 63),  # Eb belongs to C minor
        (71, 0, "minor", 71),  # and so does the raised seventh
        (64, 0, "minor", 63),
        (66, 2, "major", 66),  # F# is in D major
        (65, 2, "major", 64),  # F is not
    ],
)
def test_snapping_to_a_scale(pitch, tonic, mode, expected):
    assert snap_to_scale(pitch, tonic, mode) == expected


def test_key_names_are_read_with_sharps_flats_and_musics_dash():
    assert [tonic_pitch_class(name) for name in ("C", "F#", "Bb", "B-", "Eb", "G#")] == [0, 6, 10, 10, 3, 8]


# ── Playing it back and exporting it ───────────────────────────────────


def test_exported_midi_holds_the_raw_notes_exactly(sample):
    data = rawplay.export_midi(sample)

    mido.MidiFile(file=io.BytesIO(data))  # a valid file
    midi = pretty_midi.PrettyMIDI(io.BytesIO(data))
    notes = midi.instruments[0].notes
    assert len(notes) == len(sample.raw)
    for exported, raw in zip(notes, sample.raw):
        assert exported.pitch == raw.pitch
        assert exported.velocity == raw.velocity
        assert exported.start == pytest.approx(raw.start, abs=2e-3)
        assert exported.end == pytest.approx(raw.end, abs=2e-3)
    assert midi.estimate_tempo() > 0
    assert midi.get_tempo_changes()[1][0] == pytest.approx(sample.tempo_bpm, abs=0.5)


def test_playing_back_uses_the_instrument_asked_for():
    result = Transcription([HeardNote(60, 0, 1, 90)], 120.0, "C", "major")
    pianos = rawplay.midi_for(result.raw, 120, rawplay.INSTRUMENTS["piano"]).instruments[0].program
    synths = rawplay.midi_for(result.raw, 120, rawplay.INSTRUMENTS["synth"]).instruments[0].program
    assert pianos != synths
    with pytest.raises(ValueError):
        rawplay.render_raw(result, "kazoo")


@pytest.mark.skipif(not can_render(), reason="needs FluidSynth and a soundfont")
@pytest.mark.parametrize("instrument", ["piano", "synth"])
def test_the_hum_plays_back_as_audio_that_starts_with_the_first_note(sample, instrument):
    audio, rate = sf.read(io.BytesIO(rawplay.render_raw(sample, instrument)))

    assert len(audio) / rate >= sample.duration  # the whole hum, and a tail
    assert np.abs(audio).max() == pytest.approx(rawplay.PEAK, abs=0.01)
    first_sound = np.argmax(np.abs(audio) > 0.02) / rate
    assert first_sound < 0.15  # no lead-in: the first note is heard straight away
    quiet_after = np.abs(audio[int((sample.duration + 0.7) * rate) :])
    assert quiet_after.max() < 0.05  # and it ends
