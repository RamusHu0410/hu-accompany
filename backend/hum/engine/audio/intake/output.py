"""The contract's handoff: melody_clean.mid and melody.json, describing the same notes.

Both are written to temporary names first, read back and checked against each other, and only
then moved into place, so a half-written or mismatched pair never appears in the run directory.
"""

import json
import os

import pretty_midi

from ..errors import PipelineError
from .normalize import new_file
from .rhythm import BeatNote

STEP = "intake.write"
MIDI_NAME = "melody_clean.mid"
JSON_NAME = "melody.json"
TICKS_PER_BEAT = 480  # divides by 3 and 4, so sixteenths and triplets land on whole ticks
TIME_SIGNATURE = "4/4"


def write_melody(run_dir: str, notes: list[BeatNote], tempo: float, key: str, tuning_cents: float) -> tuple[str, str]:
    """Writes the pair and returns their paths. Raises PipelineError if they'd disagree."""
    midi_path, json_path = new_file(run_dir, MIDI_NAME, STEP), new_file(run_dir, JSON_NAME, STEP)
    melody = {
        "tempo_bpm": tempo,
        "key": key,
        "time_signature": TIME_SIGNATURE,
        "tuning_offset_cents": int(round(tuning_cents)),
        "notes": [
            {"pitch": n.pitch, "start_beats": n.start_beats, "duration_beats": n.duration_beats, "velocity": n.velocity}
            for n in notes
        ],
    }
    midi_temp, json_temp = midi_path + ".tmp", json_path + ".tmp"
    try:
        _midi_for(melody).write(midi_temp)
        with open(json_temp, "w") as file:
            json.dump(melody, file, indent=2)
        check_pair(midi_temp, json_temp)
        os.replace(midi_temp, midi_path)
        os.replace(json_temp, json_path)
    finally:
        for temp in (midi_temp, json_temp):
            if os.path.exists(temp):
                os.remove(temp)
    return midi_path, json_path


def check_pair(midi_path: str, json_path: str) -> None:
    """The MIDI must be one monophonic piano track with exactly the JSON's notes, tempo, meter and key."""
    with open(json_path) as file:
        melody = json.load(file)
    midi = pretty_midi.PrettyMIDI(midi_path)
    problems = []
    if len(midi.instruments) != 1 or midi.instruments[0].program != 0 or midi.instruments[0].is_drum:
        problems.append("the MIDI must have exactly one track, program 0")
    _, tempi = midi.get_tempo_changes()
    if len(tempi) != 1 or abs(tempi[0] - melody["tempo_bpm"]) > 0.01:
        problems.append(f"MIDI tempo {list(tempi)} is not {melody['tempo_bpm']}")
    meter = [f"{t.numerator}/{t.denominator}" for t in midi.time_signature_changes]
    if meter != [melody["time_signature"]]:
        problems.append(f"MIDI time signature {meter} is not {melody['time_signature']}")
    keys = [k.key_number for k in midi.key_signature_changes]
    if keys != [_key_number(melody["key"])]:
        problems.append(f"MIDI key signature {keys} is not {melody['key']}")
    played = sorted(midi.instruments[0].notes, key=lambda n: n.start) if midi.instruments else []
    if len(played) != len(melody["notes"]):
        problems.append(f"MIDI has {len(played)} notes, JSON has {len(melody['notes'])}")
    for i, (heard, written) in enumerate(zip(played, melody["notes"])):
        start = midi.time_to_tick(heard.start) / midi.resolution
        length = midi.time_to_tick(heard.end) / midi.resolution - start
        if (
            heard.pitch != written["pitch"]
            or heard.velocity != written["velocity"]
            or abs(start - written["start_beats"]) > 1 / midi.resolution
            or abs(length - written["duration_beats"]) > 2 / midi.resolution
        ):
            problems.append(f"note {i} differs: MIDI {heard.pitch} at {start:.4f} for {length:.4f}, JSON {written}")
    for a, b in zip(played, played[1:]):
        if b.start < a.end - 1e-6:
            problems.append("the MIDI has overlapping notes")
            break
    if problems:
        raise PipelineError(STEP, "The melody files didn't match: " + "; ".join(problems), code="mismatch")


def _midi_for(melody: dict) -> pretty_midi.PrettyMIDI:
    midi = pretty_midi.PrettyMIDI(resolution=TICKS_PER_BEAT, initial_tempo=melody["tempo_bpm"])
    numerator, denominator = (int(part) for part in melody["time_signature"].split("/"))
    midi.time_signature_changes.append(pretty_midi.TimeSignature(numerator, denominator, 0))
    midi.key_signature_changes.append(pretty_midi.KeySignature(_key_number(melody["key"]), 0))
    track = pretty_midi.Instrument(program=0, name="melody")
    seconds_per_beat = 60 / melody["tempo_bpm"]
    for note in melody["notes"]:
        start = note["start_beats"] * seconds_per_beat
        end = (note["start_beats"] + note["duration_beats"]) * seconds_per_beat
        track.notes.append(pretty_midi.Note(velocity=note["velocity"], pitch=note["pitch"], start=start, end=end))
    midi.instruments.append(track)
    return midi


def _key_number(key: str) -> int:
    """pretty_midi's number for a key named the music21 way ("B- major" is B-flat major)."""
    return pretty_midi.key_name_to_key_number(key.replace("-", "b"))
