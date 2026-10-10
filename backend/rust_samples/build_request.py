"""Turns native_ffi's JSON output into a /api/feedback/phrase request body and
checks the real backend judge accepts it.

usage (from backend/):
    python rust_samples/build_request.py <name>.rust_output.json <piece.json> <name>.phrase_request.json

<piece.json> is the PieceData fixture the Rust run was scored against
(native_ffi/fixtures/piano/rendered/<name>.json). Its notes become
`expected_notes`. The user-note mapping copies the rules of
frontend/lib/integrations/feedback/Phrase_send2_server.dart `_userNoteToJson`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feedback_generator import judge_phrase  # noqa: E402 -- needs backend/ on sys.path


def user_note_to_json(note: dict) -> dict:
    """Same rules as the Dart `_userNoteToJson`: resolve null timing, drop `is_end`."""
    start, end, duration = note.get("start_time_ms"), note.get("end_time_ms"), note.get("duration_ms")
    resolved_start = start if start is not None else 0
    resolved_duration = duration if duration is not None else (
        end - start if end is not None and start is not None else 0
    )
    resolved_end = end if end is not None else resolved_start + resolved_duration
    out = {
        "note_id": int(note["note_id"]),
        "pitch_hz": note["pitch_hz"],
        "start_time_ms": resolved_start,
        "end_time_ms": resolved_end,
        "duration_ms": resolved_duration,
    }
    if note.get("has_accent") is not None:
        out["has_accent"] = note["has_accent"]
    if note.get("volume") is not None:
        out["volume"] = note["volume"]
    return out


def main(rust_output: str, piece_path: str, request_out: str) -> None:
    rust_notes = json.loads(Path(rust_output).read_text())
    piece = json.loads(Path(piece_path).read_text())

    request = {
        "phrase": 1,
        "timing": {"bpm": piece["timing"]["bpm"], "time_signature": "4/4"},  # PieceData has no time_signature
        "piece": {"title": piece["piece_name"]},
        "expected_notes": [{k: v for k, v in n.items() if k != "is_end"} for n in piece["notes"]],
        "user_notes": [user_note_to_json(n) for n in rust_notes],
    }
    Path(request_out).write_text(json.dumps(request, indent=2) + "\n")

    result = judge_phrase(
        phrase=request["phrase"],
        bpm=request["timing"]["bpm"],
        expected_notes=request["expected_notes"],
        user_notes=request["user_notes"],
        time_signature=request["timing"]["time_signature"],
        bar_boxes=None,
    )
    print(f"{len(rust_notes)} Rust notes -> accepted; scores={result['scores']}; {len(result['feedback'])} finding(s)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
