"""Tests for diatonic chord candidate generation (Phase 7)."""

from hum.engine.accompanist.models.chord import Chord
from hum.engine.accompanist.music.chord_candidates import get_candidates


def test_chord_model_symbol():
    assert Chord("C", "major").symbol == "C"
    assert Chord("D", "minor").symbol == "Dm"
    assert Chord("B", "diminished").symbol == "Bdim"


def test_c_major_candidates():
    symbols = [c.symbol for c in get_candidates("C", "major")]
    assert symbols == ["C", "Dm", "Em", "F", "G", "Am", "Bdim"]


def test_c_major_qualities():
    chords = get_candidates("C", "major")
    assert len(chords) == 7
    assert chords[0] == Chord("C", "major")
    assert chords[1] == Chord("D", "minor")
    assert chords[6] == Chord("B", "diminished")


def test_a_minor_candidates():
    symbols = [c.symbol for c in get_candidates("A", "minor")]
    assert symbols == ["Am", "Bdim", "C", "Dm", "Em", "F", "G"]
