"""Tests for key detection (Phase 5) and melody extraction (Phase 6)."""

from hum.engine.accompanist.models.melody import Melody, Note
from hum.engine.accompanist.music.melody_to_midi import melody_to_midi
from hum.engine.accompanist.music.midi_reader import read_midi
from hum.engine.accompanist.music.key_detection import detect_key
from hum.engine.accompanist.music.melody_extractor import extract_melody


def _write(melody: Melody, path) -> str:
    melody_to_midi(melody, str(path))
    return str(path)


# ---------------------------------------------------------------------------
# Phase 5 — key detection
# ---------------------------------------------------------------------------

def test_detect_c_major(tmp_path):
    # Tonally grounded C-major line: emphasizes C-E-G, ends on a long tonic.
    pitches = [60, 64, 67, 72, 67, 64, 65, 64, 62, 60, 64, 67, 60]
    mel = Melody(notes=[Note(p, i * 0.5, 0.5) for i, p in enumerate(pitches)], tempo=120)
    mel.notes[-1].duration = 2.0

    result = detect_key(_write(mel, tmp_path / "cmaj.mid"))

    assert result.tonic.name == "C"
    assert result.mode == "major"


def test_detect_a_minor(tmp_path):
    # Tonally grounded A-minor line: emphasizes A-C-E, ends on a long tonic.
    pitches = [69, 72, 76, 81, 76, 72, 71, 72, 74, 72, 69, 71, 69]
    mel = Melody(notes=[Note(p, i * 0.5, 0.5) for i, p in enumerate(pitches)], tempo=120)
    mel.notes[-1].duration = 2.0

    result = detect_key(_write(mel, tmp_path / "amin.mid"))

    assert result.tonic.name == "A"
    assert result.mode == "minor"


# ---------------------------------------------------------------------------
# Phase 6 — melody extraction
# ---------------------------------------------------------------------------

# Original JSON (Kingsley's melody). Timing is in the melody's own units.
ORIGINAL = [
    {"pitch": 60, "start": 0.0, "duration": 0.5},
    {"pitch": 64, "start": 0.5, "duration": 0.5},
    {"pitch": 67, "start": 1.0, "duration": 1.0},
]

# tempo used when writing the MIDI (beats-per-minute)
TEMPO = 120
# quarterLength-per-second scale: at 120bpm one quarter note = 0.5s,
# so 1 second == TEMPO/60 quarter lengths.
QL_PER_SECOND = TEMPO / 60.0

TIMING_TOLERANCE = 0.05  # quarter lengths


def test_extract_matches_original(tmp_path):
    mel = Melody(
        notes=[Note(n["pitch"], n["start"], n["duration"]) for n in ORIGINAL],
        tempo=TEMPO,
    )
    score = read_midi(_write(mel, tmp_path / "round.mid"))
    extracted = extract_melody(score)

    # Same number of notes
    assert len(extracted) == len(ORIGINAL)

    for orig, got in zip(ORIGINAL, extracted):
        # Pitch must match exactly
        assert got["pitch"] == orig["pitch"]

        # Timing round-trips through MIDI in quarter-length units. Convert the
        # original (seconds) to quarter lengths for comparison.
        expected_start = orig["start"] * QL_PER_SECOND
        expected_dur = orig["duration"] * QL_PER_SECOND
        assert abs(got["start"] - expected_start) <= TIMING_TOLERANCE
        assert abs(got["duration"] - expected_dur) <= TIMING_TOLERANCE
