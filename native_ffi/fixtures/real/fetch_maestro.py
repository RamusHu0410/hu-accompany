#!/usr/bin/env python3
"""Fetch pedal-free excerpts of real piano recordings (MAESTRO) as a held-out set.

MAESTRO v3 (Hawthorne et al., ICLR 2019), CC BY-NC-SA 4.0:
https://magenta.tensorflow.org/datasets/maestro
Concert grand (Yamaha Disklavier) recorded with room mics; the Disklavier's
own MIDI is the ground truth, aligned to the audio within ~3 ms.

Only windows where the sustain (and sostenuto) pedal is never down are used,
so a note sounds exactly while its key is held. Windows also start at a moment
when no key is held, so every note in the clip has its attack in the clip.

The audio zip is 108 GB and its WAVs are deflated, so a window at time t costs
downloading ~150 KB per second of audio before it. Windows ending after
--max-end-s are skipped for that reason. Only the clips are kept.

usage: python3 fixtures/real/fetch_maestro.py [--clips N] [--max-end-s S] [--out DIR]
writes: fixtures/real/maestro_heldout/<clip>_solo|_comp.{wav,json} (PieceData)
  REAL_AUDIO_DIR=fixtures/real/maestro_heldout cargo test --release --test real_audio -- --ignored --nocapture

Held out: never tune the detector on these.
"""

import argparse
import bisect
import io
import json
import math
import struct
import subprocess
import wave
import zipfile
from pathlib import Path

from fetch_guitarset import HttpRangeFile

BASE = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0"
AUDIO_ZIP = f"{BASE}/maestro-v3.0.0.zip"
MIDI_ZIP = f"{BASE}/maestro-v3.0.0-midi.zip"
METADATA = f"{BASE}/maestro-v3.0.0.json"
HERE = Path(__file__).parent
CACHE = HERE / ".cache"
OUT_DIR = HERE / "maestro_heldout"

WINDOW_S = 30.0
TAIL_S = 1.5  # audio kept after the last key release (damper fade)
# Clips open this long before their first note: just over the detector's
# 85 ms listening margin (tracker::TIMING_MARGIN_MS). Longer makes it rarer
# that no key is held at the cut, since legato keys overlap.
LEAD_S = 0.1
MIN_NOTES = 40
PEDAL_DOWN = 64  # MIDI convention: controller value >= 64 = pedal pressed
SUSTAIN_CCS = (64, 66)  # sustain, sostenuto (soft pedal 67 doesn't prolong notes)
# A clip is "solo" if at most this share of its notes overlap another note.
SOLO_MAX_OVERLAP = 0.15


def midi_to_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---- MIDI reading ----------------------------------------------------------


def read_varlen(data, i):
    n = 0
    while True:
        b = data[i]
        i += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            return n, i


def parse_midi(data):
    """Returns (notes, pedal) in seconds: notes = [(pitch, on, off, velocity)],
    pedal = [(time, controller, value)]. Handles running status, sysex, meta
    events and tempo changes anywhere in any track."""
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    assert not division & 0x8000, "SMPTE time division not supported"
    pos, raw = 14, []  # raw = (tick, kind, a, b, c)
    for _ in range(ntracks):
        assert data[pos:pos + 4] == b"MTrk"
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        i, end, tick, status = pos + 8, pos + 8 + length, 0, 0
        while i < end:
            delta, i = read_varlen(data, i)
            tick += delta
            if data[i] & 0x80:
                status = data[i]
                i += 1
            if status == 0xFF:  # meta
                mtype = data[i]
                mlen, i = read_varlen(data, i + 1)
                if mtype == 0x51:
                    raw.append((tick, "tempo", int.from_bytes(data[i:i + 3], "big"), 0, 0))
                i += mlen
            elif status in (0xF0, 0xF7):  # sysex
                slen, i = read_varlen(data, i)
                i += slen
            else:
                kind = status & 0xF0
                size = 1 if kind in (0xC0, 0xD0) else 2
                a = data[i]
                b = data[i + 1] if size == 2 else 0
                i += size
                raw.append((tick, kind, a, b, 0))
        pos = end

    # Tempo map: ticks -> seconds (default 120 bpm until the first tempo event).
    raw.sort(key=lambda e: (e[0], e[1] != "tempo"))
    sec, last_tick, us_per_q = 0.0, 0, 500_000
    notes, pedal, held = [], [], {}
    for tick, kind, a, b, _ in raw:
        sec += (tick - last_tick) * us_per_q / 1e6 / division
        last_tick = tick
        if kind == "tempo":
            us_per_q = a
        elif kind == 0x90 and b > 0:
            if a in held:  # re-struck while held: the first strike ends here
                on, vel = held.pop(a)
                notes.append((a, on, sec, vel))
            held[a] = (sec, b)
        elif kind in (0x80, 0x90):
            if a in held:
                on, vel = held.pop(a)
                notes.append((a, on, sec, vel))
        elif kind == 0xB0 and a in SUSTAIN_CCS:
            pedal.append((sec, a, b))
    for a, (on, vel) in held.items():  # never released: end at the last event
        notes.append((a, on, sec, vel))
    notes.sort(key=lambda n: (n[1], n[0]))
    return notes, pedal


# ---- Window search ---------------------------------------------------------


def pedal_down_intervals(pedal):
    """[(start, end)] spans where any sustaining pedal is down, sorted."""
    state = {cc: 0 for cc in SUSTAIN_CCS}
    spans, down_since = [], None
    for t, cc, v in pedal:
        state[cc] = v
        down = any(x >= PEDAL_DOWN for x in state.values())
        if down and down_since is None:
            down_since = t
        elif not down and down_since is not None:
            spans.append((down_since, t))
            down_since = None
    if down_since is not None:
        spans.append((down_since, math.inf))
    return spans


def find_window(notes, pedal, max_end_s):
    """Earliest pedal-free window starting when no key is held. Candidate
    starts are LEAD_S before each note onset (so the clip opens with an attack).
    Returns (t0, audio_end, notes) with note ends clipped to audio_end."""
    notes = [n for n in notes if n[1] < max_end_s]
    if len(notes) < MIN_NOTES:
        return None
    onsets = [n[1] for n in notes]
    # prefix_max_off[k] = latest key release among notes[:k] (is a key held at t?)
    prefix_max_off = [0.0]
    for n in notes:
        prefix_max_off.append(max(prefix_max_off[-1], n[2]))
    spans = pedal_down_intervals(pedal)
    span_starts = [s for s, _ in spans]
    span_prefix_max_end = [0.0]
    for _, e in spans:
        span_prefix_max_end.append(max(span_prefix_max_end[-1], e))

    for on in onsets:
        t0 = max(0.0, on - LEAD_S)
        first = bisect.bisect_left(onsets, t0)
        last = bisect.bisect_left(onsets, t0 + WINDOW_S)
        if last - first < MIN_NOTES or prefix_max_off[first] > t0:
            continue  # too few notes, or a key held from before is still down
        # Stop at the next note after the window, so no unscored note sounds.
        audio_end = max(n[2] for n in notes[first:last]) + TAIL_S
        if last < len(onsets):
            audio_end = min(audio_end, onsets[last])
        if audio_end > max_end_s:
            return None  # later windows only cost more to download
        k = bisect.bisect_left(span_starts, audio_end)
        if span_prefix_max_end[k] > t0:
            continue  # some pedal-down span overlaps [t0, audio_end]
        return t0, audio_end, [(p, s, min(e, audio_end), v) for p, s, e, v in notes[first:last]]
    return None


def overlap_share(notes):
    """Share of notes that overlap another note in time (chords, voices)."""
    overlapping = 0
    for i, (_, on, off, _) in enumerate(notes):
        if any(j != i and o < off and on < f for j, (_, o, f, _) in enumerate(notes)):
            overlapping += 1
    return overlapping / len(notes)


# ---- Audio -----------------------------------------------------------------


def read_wav_window(member, t0, t1):
    """Reads [t0, t1) seconds of PCM from a (streamed, deflated) WAV member."""
    assert member.read(12)[8:12] == b"WAVE"
    fmt = None
    while True:
        cid, size = struct.unpack("<4sI", member.read(8))
        if cid == b"fmt ":
            body = member.read(size)
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = (channels, rate, bits)
        elif cid == b"data":
            break
        else:
            member.read(size + (size & 1))
    channels, rate, bits = fmt
    frame = channels * bits // 8
    skip = int(t0 * rate) * frame
    while skip:
        skip -= len(member.read(min(skip, 1 << 20)))
    pcm = member.read(int((t1 - t0) * rate) * frame)
    return pcm, channels, rate, bits


def onset_alignment_ms(pcm, channels, rate, bits, onsets_s):
    """Median lag between score onsets and energy rises in the audio: checks
    that the clip and its score line up (a wrong t0 or rate shows up here)."""
    assert bits == 16
    hop = rate // 200  # 5 ms
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    mono = samples[::channels]
    energy = [math.log(1e-9 + sum(s * s for s in mono[i:i + hop])) for i in range(0, len(mono) - hop, hop)]
    flux = [max(0.0, energy[i] - energy[i - 1]) for i in range(1, len(energy))]
    lags = []
    for t in onsets_s:
        c = int(t * 200)
        lo, hi = max(1, c - 10), min(len(flux) - 1, c + 10)  # ±50 ms
        if lo < hi:
            best = max(range(lo, hi), key=lambda k: flux[k])
            lags.append((best - c) * 5)
    lags.sort()
    return lags[len(lags) // 2] if lags else None


# ---- Output ----------------------------------------------------------------


def piece_json(name, notes, t0):
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
                "start_time_ms": round((on - t0) * 1000, 1),
                "end_time_ms": round((off - t0) * 1000, 1),
                "duration_ms": round((off - on) * 1000, 1),
                "is_end": i == len(notes) - 1,
                "vibrato_depth": None,
                "pedal_action": None,
                "has_accent": None,
                "markings": None,
            }
            for i, (p, on, off, _) in enumerate(notes)
        ],
    }


def fetch(url, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url.rsplit('/', 1)[1]} -> {path}")
        subprocess.run(["curl", "-sfL", "-o", str(path), url], check=True)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", type=int, default=3, help="clips per kind (solo and comp)")
    parser.add_argument("--max-end-s", type=float, default=150.0, help="skip windows ending later (download cost)")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    meta = json.loads(fetch(METADATA, CACHE / "maestro-v3.0.0.json").read_text())
    rows = sorted(
        ({k: meta[k][i] for k in ("canonical_composer", "canonical_title", "midi_filename", "audio_filename")}
         for i in meta["midi_filename"]),
        key=lambda r: r["midi_filename"],
    )
    midi_zip = zipfile.ZipFile(fetch(MIDI_ZIP, CACHE / "maestro-v3.0.0-midi.zip"))
    midi_names = {Path(n).name: n for n in midi_zip.namelist()}

    print(f"scanning {len(rows)} performances for pedal-free windows ending by {args.max_end_s:.0f} s...")
    found = {"solo": [], "comp": []}
    for r in rows:
        notes, pedal = parse_midi(midi_zip.read(midi_names[Path(r["midi_filename"]).name]))
        w = find_window(notes, pedal, args.max_end_s)
        if w:
            kind = "solo" if overlap_share(w[2]) <= SOLO_MAX_OVERLAP else "comp"
            found[kind].append((r, w))
    print(f"  candidates: {len(found['solo'])} solo, {len(found['comp'])} comp")

    # Spread picks across composers; prefer the cheapest downloads.
    picks = []
    for kind, cands in found.items():
        cands.sort(key=lambda c: c[1][1])
        composers = set()
        for r, w in cands:
            if len([p for p in picks if p[0] == kind]) == args.clips:
                break
            if r["canonical_composer"] in composers:
                continue
            composers.add(r["canonical_composer"])
            picks.append((kind, r, w))

    args.out.mkdir(parents=True, exist_ok=True)
    audio_zip = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(AUDIO_ZIP), buffer_size=4 << 20))
    audio_names = {Path(n).name: n for n in audio_zip.namelist()}
    credits = []
    for n, (kind, r, (t0, t1, notes)) in enumerate(picks):
        composer = r["canonical_composer"].split()[-1].split("/")[0]
        name = f"{n:02d}_{composer}_{kind}"
        wav_out, json_out = args.out / f"{name}.wav", args.out / f"{name}.json"
        credits.append(f"{name}: {r['canonical_composer']} - {r['canonical_title']} "
                       f"({r['audio_filename']}, {t0:.2f}-{t1:.2f} s)")
        if wav_out.exists() and json_out.exists():
            print(f"  have {name}")
            continue
        print(f"  fetching {name}: {r['canonical_title'][:50]} @ {t0:.1f}-{t1:.1f} s ({len(notes)} notes)")
        with audio_zip.open(audio_names[Path(r["audio_filename"]).name]) as member:
            pcm, channels, rate, bits = read_wav_window(member, t0, t1)
        lag = onset_alignment_ms(pcm, channels, rate, bits, [on - t0 for _, on, _, _ in notes])
        assert lag is not None and abs(lag) <= 20, f"{name}: audio/score misaligned by {lag} ms"
        with wave.open(str(wav_out), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(bits // 8)
            w.setframerate(rate)
            w.writeframes(pcm)
        json_out.write_text(json.dumps(piece_json(name, notes, t0), indent=1))
        print(f"    {rate} Hz {channels} ch, onset alignment {lag:+d} ms")

    (args.out / "ATTRIBUTION.txt").write_text(
        "MAESTRO v3.0.0: C. Hawthorne et al., 'Enabling Factorized Piano Music Modeling and "
        "Generation with the MAESTRO Dataset', ICLR 2019.\n"
        "https://magenta.tensorflow.org/datasets/maestro  License: CC BY-NC-SA 4.0\n\n"
        + "\n".join(credits) + "\n"
    )
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
