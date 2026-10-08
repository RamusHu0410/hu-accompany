#!/usr/bin/env bash
# Posts the deliberately-imperfect sample phrase to a locally running
# backend and pretty-prints the judgment, so the phase-1 pipeline can be
# exercised end to end without working Rust audio capture.
#
#   ./post_sample_phrase.sh                  # 127.0.0.1:8000
#   ./post_sample_phrase.sh 192.168.1.20     # from a phone on the LAN
#                                            # (host: `ipconfig getifaddr en0`)
#
# Start the server first, per the README:
#   cd backend && DYLD_LIBRARY_PATH=/opt/homebrew/lib python manage.py runserver 0.0.0.0:8000
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE="$HERE/phrase_imperfect.json"

echo "POST http://$HOST:$PORT/api/feedback/phrase  <-  $(basename "$SAMPLE")"
echo

curl -s -X POST "http://$HOST:$PORT/api/feedback/phrase" \
  -H "Content-Type: application/json" \
  -d @"$SAMPLE" | python3 -m json.tool

echo
echo "The sample is imperfect on purpose, so a 100/100 means something is wrong."
echo "Expect findings for: note 2 a semitone sharp, note 3 ~180 ms late,"
echo "note 4 clipped to about half length, note 6 never played, and an extra"
echo "F#4 that is not in the score."
echo
echo "To summarize everything stored under the session id it returns:"
echo "  curl -s -X POST http://$HOST:$PORT/api/feedback/summary \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"session_id\": \"<session_id from above>\"}' | python3 -m json.tool"
