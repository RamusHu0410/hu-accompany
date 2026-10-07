"""The intake's pieces on their own: the guardrail, the beat grid, and the MIDI/JSON check."""

import json

import numpy as np
import pretty_midi
import pytest

from hum.engine.audio.intake import PipelineError
from hum.engine.audio.intake.cleanup import Note, clean_melody, lightly_filtered
from hum.engine.audio.intake.output import check_pair, write_melody
from hum.engine.audio.intake.rhythm import BeatNote, detect_tempo, quantize, snap
from hum.engine.audio.intake.transcribe import RawNote, Transcription


def _raw(*notes):
    return [RawNote(start, end, pitch, 0.6) for start, end, pitch in notes]


def test_the_guardrail_falls_back_to_the_lightly_filtered_notes():
    # a contour with nothing in it: the cleanup finds no notes, so the raw ones are used
    raw = _raw((0.0, 0.5, 50), (0.5, 1.0, 52), (1.0, 1.02, 70), (1.0, 1.5, 53))
    frames = np.arange(0, 1.6, 0.0116)
    heard = Transcription(raw, np.zeros((len(frames), 264)), frames)
    cleaned = clean_melody(heard, np.zeros(22050), 22050)
    assert cleaned.fell_back
    assert [n.pitch for n in cleaned.notes] == [50, 52, 53]  # the 20 ms fragment is gone
    assert any("hard to make out" in warning for warning in cleaned.warnings)  # plain words: users may see it


def test_light_filtering_keeps_one_note_at_a_time_and_joins_straight_repeats():
    raw = _raw((0.0, 0.5, 50), (0.1, 0.3, 62), (0.5, 1.0, 50), (1.0, 1.5, 53))
    kept = lightly_filtered(raw)
    assert [(n.pitch, n.start, n.end) for n in kept] == [(50, 0.0, 1.0), (53, 1.0, 1.5)]


@pytest.mark.parametrize(("beats", "grid"), [(1.02, 1.0), (1.49, 1.5), (0.74, 0.75), (2.34, 7 / 3), (2.67, 8 / 3)])
def test_snapping_uses_sixteenths_or_clear_triplets(beats, grid):
    assert snap(beats) == pytest.approx(grid)


def test_quantizing_keeps_notes_in_order_and_apart():
    seconds = 60 / 100
    notes = [Note(0.0, 0.98 * seconds, 50), Note(1.01 * seconds, 1.52 * seconds, 52), Note(1.52 * seconds, 2.9 * seconds, 53)]
    beats = quantize(notes, 100)
    assert [(n.start_beats, n.duration_beats) for n in beats] == [(0.0, 1.0), (1.0, 0.5), (1.5, 1.5)]


def test_tempo_prefers_the_grid_the_notes_fit_not_double_or_half():
    seconds = 60 / 92
    starts = [0, 1, 2, 2.5, 3, 4, 4.75, 5, 6]
    notes = [Note(b * seconds, b * seconds + 0.2, 50) for b in starts]
    assert detect_tempo(notes) == pytest.approx(92, abs=1)


def test_a_midi_and_json_that_disagree_are_caught(tmp_path):
    midi_path, json_path = write_melody(str(tmp_path), [BeatNote(50, 0, 1, 80), BeatNote(52, 1, 1, 80)], 92.0, "D minor", 14)
    check_pair(midi_path, json_path)
    assert pretty_midi.PrettyMIDI(midi_path).key_signature_changes[0].key_number == pretty_midi.key_name_to_key_number("D minor")
    with open(json_path) as file:
        melody = json.load(file)
    melody["notes"][1]["pitch"] = 53
    with open(json_path, "w") as file:
        json.dump(melody, file)
    with pytest.raises(PipelineError, match="didn't match") as mismatch:
        check_pair(midi_path, json_path)
    assert mismatch.value.code == "mismatch"


def test_a_flat_key_written_the_music21_way_gets_its_key_signature(tmp_path):
    midi_path, json_path = write_melody(str(tmp_path), [BeatNote(58, 0, 1, 80), BeatNote(62, 1, 1, 80)], 100.0, "B- major", 0)
    check_pair(midi_path, json_path)
    assert pretty_midi.PrettyMIDI(midi_path).key_signature_changes[0].key_number == pretty_midi.key_name_to_key_number("Bb major")


def test_an_octave_ghost_a_semitone_off_joins_the_note_around_it():
    # basic-pitch heard A4 over an A3; after the tuning correction it rounded to G#4 (11 semitones up)
    from hum.engine.audio.intake.cleanup import _join_fragments
    from hum.engine.audio.intake.config import CLEANUP

    notes = [Note(0.0, 0.5, 57), Note(0.5, 0.59, 68), Note(0.59, 1.0, 57)]
    assert [n.pitch for n in _join_fragments(notes, CLEANUP)] == [57, 57]


def test_a_note_the_grid_squeezes_below_80_ms_joins_the_one_before():
    seconds = 60 / 170
    # a triplet start and a sixteenth start next to each other leave a sixth of a beat (59 ms at 170 BPM)
    notes = [Note(0.0, 8.33 * seconds, 57), Note(8.33 * seconds, 8.5 * seconds, 60), Note(8.5 * seconds, 9.5 * seconds, 57)]
    beats = quantize(notes, 170)
    assert all(n.duration_beats * seconds >= 0.08 for n in beats)
    assert [n.pitch for n in beats] == [57, 57]
