#!/usr/bin/env python3
"""Fetch a few real GuitarSet recordings + note annotations for the real-audio test.

GuitarSet (Xi et al., ISMIR 2018), CC BY 4.0: https://zenodo.org/records/3371780
Acoustic guitar recorded with a room microphone, annotated note-by-note.
"solo" takes are single-note melodies, "comp" takes are strummed/plucked chords.

Only the requested clips are pulled out of the 657 MB zip using HTTP range
requests, so the download is a few MB. Standard library + the `curl` CLI
(curl uses the OS certificate store; python.org builds on macOS ship without one).

usage: python3 fixtures/real/fetch_guitarset.py [--clips N] [--skip K] [--out DIR]
writes: fixtures/real/guitarset/<clip>.wav + <clip>.json (PieceData for the harness)

Held-out set (clips never used for tuning):
  python3 fixtures/real/fetch_guitarset.py --skip 3 --out fixtures/real/guitarset_heldout
  REAL_AUDIO_DIR=fixtures/real/guitarset_heldout cargo test --test real_audio -- --ignored --nocapture
"""

import argparse
import io
import json
import subprocess
import zipfile
from pathlib import Path

RECORD = "https://zenodo.org/api/records/3371780/files"
AUDIO_ZIP = f"{RECORD}/audio_mono-mic.zip/content"
ANNOTATION_ZIP = f"{RECORD}/annotation.zip/content"
OUT_DIR = Path(__file__).parent / "guitarset"


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file; zipfile only fetches what it reads."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        headers = subprocess.run(
            ["curl", "-sfIL", url], check=True, capture_output=True, text=True
        ).stdout
        lengths = [l for l in headers.splitlines() if l.lower().startswith("content-length:")]
        self.size = int(lengths[-1].split(":")[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        data = subprocess.run(
            ["curl", "-sfL", "-r", f"{self.pos}-{end}", self.url], check=True, capture_output=True
        ).stdout
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def midi_to_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def jams_to_piece(jams, name):
    """Converts GuitarSet's per-string note_midi annotations into our PieceData JSON.

    The annotations are aligned to the actual performance, so score time ==
    recording time and no --offset-ms is needed.
    """
    notes = []
    for ann in jams["annotations"]:
        if ann["namespace"] != "note_midi":
            continue
        for obs in ann["data"]:
            start_ms = obs["time"] * 1000.0
            dur_ms = obs["duration"] * 1000.0
            notes.append((start_ms, dur_ms, obs["value"]))
    notes.sort()
    return {
        "piece_name": name,
        "curr_phase": 0,
        "instrument": "Guitar",
        "curr_music_phrase": 0,
        "timing": {"bpm": float(jams["file_metadata"].get("tempo") or 120), "beat_unit": 4},
        "notes": [
            {
                "note_id": i + 1,
                "pitch_hz": round(midi_to_hz(m), 3),
                "start_time_ms": round(s, 1),
                "end_time_ms": round(s + d, 1),
                "duration_ms": round(d, 1),
                "is_end": i == len(notes) - 1,
                "vibrato_depth": None,
                "pedal_action": None,
                "has_accent": None,
                "markings": None,
            }
            for i, (s, d, m) in enumerate(notes)
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", type=int, default=3, help="clips per kind (solo and comp)")
    parser.add_argument("--skip", type=int, default=0, help="shift picks to get different takes")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    args = parser.parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("reading zip directories (a few range requests)...")
    audio_zip = zipfile.ZipFile(HttpRangeFile(AUDIO_ZIP))
    annotation_zip = zipfile.ZipFile(HttpRangeFile(ANNOTATION_ZIP))
    annotations = {Path(n).stem: n for n in annotation_zip.namelist() if n.endswith(".jams")}

    # Spread picks across players AND styles (bossa nova, funk, jazz, rock,
    # singer-songwriter). Sorted names are <player>_<style><n>-<tempo>-<key>, so a
    # plain stride would pick the same excerpt from each player; offset each pick.
    for kind in ("solo", "comp"):
        wavs = sorted(n for n in audio_zip.namelist() if n.endswith(f"_{kind}_mic.wav"))
        step = max(1, len(wavs) // args.clips)
        picks = [wavs[(i * step + i * 7 + args.skip) % len(wavs)] for i in range(min(args.clips, len(wavs)))]
        for wav_name in picks:
            clip = Path(wav_name).stem.removesuffix("_mic")  # e.g. 00_BN1-129-Eb_solo
            wav_out, json_out = out_dir / f"{clip}.wav", out_dir / f"{clip}.json"
            if wav_out.exists() and json_out.exists():
                print(f"  have {clip}")
                continue
            print(f"  fetching {clip}")
            wav_out.write_bytes(audio_zip.read(wav_name))
            jams = json.loads(annotation_zip.read(annotations[clip]))
            json_out.write_text(json.dumps(jams_to_piece(jams, clip), indent=1))

    (out_dir / "ATTRIBUTION.txt").write_text(
        "GuitarSet: Q. Xi, R. Bittner, J. Pauwels, X. Ye, J. P. Bello. "
        "'GuitarSet: A Dataset for Guitar Transcription', ISMIR 2018.\n"
        "https://zenodo.org/records/3371780  License: CC BY 4.0\n"
    )
    print(f"done -> {out_dir}")


if __name__ == "__main__":
    main()
