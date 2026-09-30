#!/usr/bin/env python3
"""Render graded, pedal-free piano test pieces for the real-audio benchmark.

Each piece is written as MIDI, rendered to WAV by fluidsynth with a sampled
grand piano, and described as PieceData JSON whose times ARE the audio times
(no --offset-ms needed). Names end in _solo (one note at a time) or _comp
(chords / several voices), the layout tests/real_audio.rs expects:

  python3 fixtures/piano/make_rendered.py
  REAL_AUDIO_DIR=fixtures/piano/rendered cargo test --release --test real_audio -- --ignored --nocapture

No sustain pedal anywhere: every note ends when its key is released, so the
score end is also a clean ground truth for durations. Reverb and chorus are
off: this set isolates the detector; room sound comes from the MAESTRO set.

Soundfont: YDP-GrandPiano (Yamaha grand samples, CC BY 3.0, FreePats),
downloaded once (~37 MB). Needs the `fluidsynth` CLI (brew install fluid-synth).
"""

import argparse
import json
import struct
import subprocess
import tarfile
import wave
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "rendered"
SF_DIR = HERE / "soundfont"
SF_URL = "https://freepats.zenvoid.org/Piano/YDP-GrandPiano/YDP-GrandPiano-SF2-20160804.tar.bz2"
SAMPLE_RATE = 44100
LEAD_IN_MS = 500  # silence before the first note so its attack isn't clipped
TAIL_MS = 1500  # render past the last key release so the damper fade is kept

C4 = 60  # MIDI note numbers: 60 = middle C, +1 = one semitone


def midi_to_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---- Pieces: lists of (midi, start_ms, end_ms, velocity), before lead-in ----


def seq(pitches, step_ms, hold=0.9, vel=80, t0=0):
    """One note per step; each held for `hold` of the step (1.0 = legato)."""
    return [(p, t0 + i * step_ms, t0 + i * step_ms + hold * step_ms, vel) for i, p in enumerate(pitches)]


def chords(chord_list, step_ms, hold=0.9, vel=75, t0=0):
    """Block chords, all notes of a chord struck together."""
    return [(p, t0 + i * step_ms, t0 + i * step_ms + hold * step_ms, vel)
            for i, chord in enumerate(chord_list) for p in chord]


MAJOR = [0, 2, 4, 5, 7, 9, 11]
C_MAJOR_2OCT = [C4 + 12 * o + s for o in range(2) for s in MAJOR] + [C4 + 24]
ODE = [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62]  # Ode to Joy (E E F G ...)


def piece_scale():
    return seq(C_MAJOR_2OCT + C_MAJOR_2OCT[-2::-1], 250)


def piece_repeated():
    # Same pitch struck again: the repeat must be a new note, not the old one's tail.
    notes = []
    t = 0
    for p, step, hold in [(60, 300, 0.8), (67, 200, 0.7), (72, 150, 0.6), (55, 250, 0.9), (76, 120, 0.5)]:
        notes += seq([p] * 4, step, hold, t0=t)
        t += 4 * step + 300
    return notes


def piece_legato_staccato():
    # hold 1.0: each key released exactly as the next is struck (incl. E-E repeats).
    legato = seq(ODE, 350, hold=1.0)
    staccato = seq(ODE, 350, hold=0.35, t0=len(ODE) * 350 + 700)
    return legato + staccato


def piece_bass():
    # Low register, including semitone steps (the neighbours the detector must reject).
    return seq([33, 36, 40, 41, 43, 45, 44, 45, 47, 48, 47, 48], 500, vel=90)


def piece_dynamics():
    # Wide leaps and soft/loud touches.
    pitches = [48, 72, 55, 79, 60, 84, 67, 91, 64, 52, 76, 57]
    vels = [40, 100, 55, 110, 35, 90, 70, 60, 45, 105, 50, 85]
    return [(p, i * 400, i * 400 + 340, v) for i, (p, v) in enumerate(zip(pitches, vels))]


def piece_block_triads():
    # I IV V I, root position then inversions, mid register.
    prog = [[60, 64, 67], [65, 69, 72], [67, 71, 74], [60, 64, 67],
            [64, 67, 72], [69, 72, 77], [62, 67, 71], [67, 72, 76]]
    return chords(prog, 800)


def piece_melody_over_chords():
    # Beginner texture: right-hand melody in quarters, left-hand triads in halves.
    melody = seq(ODE + [62, 60], 400, hold=0.9, vel=85)
    lh = [[48, 52, 55], [43, 47, 50], [48, 52, 55], [43, 47, 50],
          [48, 52, 55], [41, 45, 48], [43, 47, 50], [48, 52, 55], [48, 52, 55]]
    return melody + chords(lh, 800, hold=0.95, vel=60)


def piece_clusters():
    # Chords containing semitone neighbours: both must be accepted, not treated as rivals.
    prog = [[60, 61, 64], [64, 65, 69], [59, 60, 64], [66, 67, 71], [71, 72, 76], [52, 53, 57]]
    return chords(prog, 900)


def piece_alberti():
    # Left hand C-G-E-G broken chords (each note held one step) under a slow melody.
    lh_pattern = [[48, 55, 52, 55], [47, 55, 50, 55], [48, 55, 52, 55], [48, 53, 57, 53]]
    lh = seq([p for bar in lh_pattern for p in bar * 2], 180, hold=1.0, vel=60)
    melody = seq([72, 74, 76, 77, 76, 74, 72, 77], 720, hold=0.95, vel=85)
    return lh + melody


def piece_sevenths_and_repeats():
    # Wide 4-note voicings (bass root + upper chord), each struck twice.
    prog = [[36, 64, 67, 71], [41, 64, 69, 72], [43, 65, 71, 74], [36, 64, 67, 72]]
    return chords([c for c in prog for _ in range(2)], 600, hold=0.85)


PIECES = {
    "01_scale_solo": piece_scale,
    "02_repeated_solo": piece_repeated,
    "03_legato_staccato_solo": piece_legato_staccato,
    "04_bass_solo": piece_bass,
    "05_dynamics_solo": piece_dynamics,
    "11_block_triads_comp": piece_block_triads,
    "12_melody_over_chords_comp": piece_melody_over_chords,
    "13_clusters_comp": piece_clusters,
    "14_alberti_comp": piece_alberti,
    "15_sevenths_repeats_comp": piece_sevenths_and_repeats,
}


# ---- MIDI (Standard MIDI File, format 0) -----------------------------------
# 1000 ticks per quarter at 1,000,000 us per quarter: 1 tick = 1 ms exactly,
# so there is no rounding between the JSON times and the audio.


def varlen(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def write_midi(notes, path):
    events = []  # (tick, order, bytes); order 0 = note-off first at equal ticks
    for p, s, e, v in notes:
        events.append((round(s), 1, bytes([0x90, p, v])))
        events.append((round(e), 0, bytes([0x80, p, 0])))
    events.sort(key=lambda ev: (ev[0], ev[1]))
    end_tick = max(t for t, _, _ in events) + TAIL_MS
    track = varlen(0) + b"\xff\x51\x03" + (1_000_000).to_bytes(3, "big")  # tempo
    track += varlen(0) + bytes([0xC0, 0])  # program 0: acoustic grand
    last = 0
    for tick, _, data in events:
        track += varlen(tick - last) + data
        last = tick
    track += varlen(end_tick - last) + b"\xff\x2f\x00"  # end of track = render length
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 1000)
    path.write_bytes(header + b"MTrk" + struct.pack(">I", len(track)) + track)


# ---- Rendering + score JSON --------------------------------------------------


def ensure_soundfont():
    found = sorted(SF_DIR.glob("**/*.sf2"))
    if found:
        return found[0]
    SF_DIR.mkdir(parents=True, exist_ok=True)
    archive = SF_DIR / "ydp.tar.bz2"
    print(f"downloading soundfont (~37 MB) -> {SF_DIR}")
    # curl uses the OS certificate store; python.org builds on macOS ship without one.
    subprocess.run(["curl", "-sfL", "-o", str(archive), SF_URL], check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(SF_DIR, filter="data")
    archive.unlink()
    found = sorted(SF_DIR.glob("**/*.sf2"))
    if not found:
        raise SystemExit(f"no .sf2 inside {SF_URL}")
    return found[0]


def render(mid, wav, soundfont):
    subprocess.run(
        ["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.6",
         "-r", str(SAMPLE_RATE), "-O", "s16", "-T", "wav", "-F", str(wav), str(soundfont), str(mid)],
        check=True,
    )


def piece_json(name, notes):
    ordered = sorted(notes, key=lambda n: (n[1], n[0]))
    return {
        "piece_name": name,
        "curr_phase": 0,
        "instrument": "Piano",
        "curr_music_phrase": 0,
        "timing": {"bpm": 120.0, "beat_unit": 4},
        "notes": [
            {
                "note_id": i + 1,
                "pitch_hz": round(midi_to_hz(p), 3),
                "start_time_ms": round(s, 1),
                "end_time_ms": round(e, 1),
                "duration_ms": round(e - s, 1),
                "is_end": i == len(ordered) - 1,
                "vibrato_depth": None,
                "pedal_action": None,
                "has_accent": None,
                "markings": None,
            }
            for i, (p, s, e, _) in enumerate(ordered)
        ],
    }


def first_sound_ms(wav, threshold_dbfs=-50.0):
    """Time of the first sample above threshold: checks MIDI -> audio alignment."""
    with wave.open(str(wav)) as w:
        assert w.getsampwidth() == 2, "expected 16-bit output"
        ch, rate = w.getnchannels(), w.getframerate()
        raw = w.readframes(w.getnframes())
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    limit = 32768 * 10 ** (threshold_dbfs / 20)
    for i, s in enumerate(samples):
        if abs(s) > limit:
            return (i // ch) * 1000.0 / rate
    return None


def validate(name, notes):
    """Score sanity: no overlapping same-pitch notes (MIDI can't play those),
    every note inside the piano's range and longer than zero."""
    by_pitch = {}
    for p, s, e, _ in notes:
        assert 21 <= p <= 108, f"{name}: MIDI {p} outside the piano"
        assert e > s, f"{name}: note {p} at {s} has no length"
        by_pitch.setdefault(p, []).append((s, e))
    for p, spans in by_pitch.items():
        spans.sort()
        for (s1, e1), (s2, _) in zip(spans, spans[1:]):
            assert e1 <= s2, f"{name}: MIDI {p} struck at {s2} while still held ({s1}-{e1})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--soundfont", type=Path, help="use this .sf2 instead of downloading YDP")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    soundfont = args.soundfont or ensure_soundfont()
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"soundfont: {soundfont}")

    for name, make in PIECES.items():
        # Whole milliseconds: MIDI ticks are 1 ms, and the JSON must match the audio exactly.
        notes = [(p, round(s) + LEAD_IN_MS, round(e) + LEAD_IN_MS, v) for p, s, e, v in make()]
        validate(name, notes)
        mid, wav, js = (args.out / f"{name}{ext}" for ext in (".mid", ".wav", ".json"))
        write_midi(notes, mid)
        render(mid, wav, soundfont)
        js.write_text(json.dumps(piece_json(name, notes), indent=1))

        # The first audible sample must line up with the first score onset;
        # a tick/tempo mistake would shift or stretch every note.
        onset = first_sound_ms(wav)
        expected = min(s for _, s, _, _ in notes)
        assert onset is not None and abs(onset - expected) < 15, f"{name}: audio starts at {onset} ms, score at {expected} ms"
        print(f"  {name:<28} {len(notes):>3} notes  first sound {onset:.1f} ms (score {expected:.0f})")

    (args.out / "ATTRIBUTION.txt").write_text(
        "Rendered with YDP-GrandPiano (FreePats, CC BY 3.0): " + SF_URL + "\n"
    )
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
