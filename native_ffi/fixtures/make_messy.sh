#!/usr/bin/env bash
# Makes "real-world" variants of a clean recording for the replay harness.
# usage: fixtures/make_messy.sh <clean.wav> <out_dir>
set -euo pipefail
in="$1"; out="$2"; mkdir -p "$out"
ff() { ffmpeg -hide_banner -loglevel error -y "$@"; }

ff -i "$in" -ar 48000 -ac 2 "$out/48k_stereo.wav"                         # iPad / audio interface
ff -i "$in" -af "volume=-24dB" "$out/quiet.wav"                          # far from the mic
ff -i "$in" -af "volume=12dB,alimiter=limit=0.9" "$out/loud_clipped.wav"   # too close to the mic
ff -i "$in" -af "aecho=0.8:0.7:40|70|110:0.4|0.3|0.2" "$out/reverb.wav"   # echoey room
ff -i "$in" -filter_complex \
  "anoisesrc=color=pink:amplitude=0.03:d=30[n];[0:a][n]amix=inputs=2:duration=first:normalize=0" \
  "$out/room_noise.wav"                                                   # fan / traffic hiss
ff -i "$in" -af "adelay=1300" "$out/late_start_1300ms.wav"                # replay with --offset-ms 1300
ff -i "$in" -af "vibrato=f=5.5:d=0.3" "$out/vibrato.wav"                  # string/voice vibrato
echo "wrote variants to $out"
