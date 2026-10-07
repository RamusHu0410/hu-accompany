import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from feedback_generator import judge_phrase, judge_piece
from feedback_generator import store as feedback_store
from feedback_generator.errors import InvalidNoteData, InvalidSessionId, StorageFailed


@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request: HttpRequest):
    try:
        body = json.loads(request.body)
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return JsonResponse({"error": "prompt is required"}, status=400)
        return JsonResponse({"response": prompt})
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def phrase_feedback_view(request):
    """POST /api/feedback/phrase — phase 1: compare one recorded phrase's
    detected user notes against the corresponding expected-performance notes
    (same schema as pdf_processor's piece_data notes / native_ffi's Notes
    struct) and return that phrase's feedback: one finding per significant
    pitch/rhythm/tempo/articulation/missing/extra problem, each tagged with
    the bar it happened in, plus 0-100 per-dimension scores.

    Phase 1 is deliberately bar-by-bar only -- no summary. Summarizing every
    phrase is phase 2 (/api/feedback/summary). One judge per dimension owns
    both its rating and its wording (feedback_generator/judges/); the
    orchestrator only wires them together. "dynamics" and "pedaling" score
    null because nothing upstream carries loudness or pedal data — see
    feedback_generator/README.md.

    Each phrase is written to
    storage/feedback/<date>-<piece>/Phase1/Phrase<n>.json
    (feedback_generator.store) -- there is no DB table for feedback. The
    session directory defaults to today's date plus the piece title, so
    consecutive phrases of the same piece group themselves; pass
    `session_id` to target one explicitly. Re-sending a phrase number
    overwrites that phrase's file. Saving is best-effort: if the write fails
    the feedback is still returned, with the reason in `storage_error`.

    Body: {"phrase": int >= 1,
           "timing": {"bpm": float, "time_signature": "4/4" (optional,
             used to number bars)},
           "expected_notes": [ {note_id, pitch_hz, start_time_ms,
             end_time_ms, duration_ms, vibrato_depth, pedal_action,
             has_accent, markings}, ... ],
           "user_notes": [ {note_id, pitch_hz, start_time_ms, end_time_ms,
             duration_ms, has_accent}, ... ],
           "bar_boxes": [ {bar, page, x, y, w, h, page_size}, ... ]
             (optional -- the piece's <Piece>_bars.json, written by
             pdf_processor; each finding then also carries `box`, the pixel
             rectangle of its bar on the rendered score, for the frontend to
             highlight. Omit it and every `box` is null),
           "session_id": str (optional),
           "piece": {...} (optional, stored as-is -- e.g. title, composer,
             composed_date, which phase 2's era judge reads back)}
    `expected_notes` must be non-empty. `user_notes` may be empty (silence
    -> every expected note comes back as a missing-note finding).

    Response: judge_phrase()'s dict plus "session_id" and "stored_at"
    (a storage/... path), or "storage_error" if it couldn't be saved, plus
    "bar_boxes" -- the piece's full bar-box list echoed back (the same
    `bar_boxes` that came in, or [] if none), so the caller has every bar's
    pixel rectangle and not only the ones a finding landed in.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    phrase = body.get("phrase")
    timing = body.get("timing") or {}
    bpm = timing.get("bpm")
    time_signature = timing.get("time_signature")
    expected_notes = body.get("expected_notes")
    user_notes = body.get("user_notes")
    bar_boxes = body.get("bar_boxes")
    session_id = body.get("session_id")
    piece = body.get("piece")

    if not isinstance(phrase, int) or isinstance(phrase, bool) or phrase < 1:
        return JsonResponse({"error": "phrase (int >= 1) is required"}, status=400)
    if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or bpm <= 0:
        return JsonResponse(
            {"error": "timing.bpm (positive number) is required"}, status=400
        )
    if not isinstance(expected_notes, list) or not expected_notes:
        return JsonResponse(
            {"error": "expected_notes (non-empty list) is required"}, status=400
        )
    if not isinstance(user_notes, list):
        return JsonResponse({"error": "user_notes (list) is required"}, status=400)
    if piece is not None and not isinstance(piece, dict):
        return JsonResponse({"error": "piece must be an object"}, status=400)
    if bar_boxes is not None and not isinstance(bar_boxes, list):
        return JsonResponse({"error": "bar_boxes must be a list"}, status=400)
    if session_id is not None:
        try:
            feedback_store.validate_session_id(session_id)
        except InvalidSessionId as e:
            return JsonResponse({"error": str(e)}, status=400)

    try:
        result = judge_phrase(
            phrase=phrase,
            bpm=bpm,
            expected_notes=expected_notes,
            user_notes=user_notes,
            time_signature=time_signature,
            bar_boxes=bar_boxes,
        )
    except InvalidNoteData as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    # Persisting is best-effort: a full disk shouldn't cost the user their
    # feedback, so a failed write is reported alongside the result.
    # Done before merging bar_boxes below, so the stored phase-1 file keeps
    # only the per-finding `box` and isn't bloated with the whole page list.
    try:
        session_id, stored_path = feedback_store.save_phrase(
            settings.STORAGE_ROOT, result, session_id=session_id, piece=piece
        )
        result["session_id"] = session_id
        result["stored_at"] = _storage_path(stored_path)
    except (StorageFailed, OSError) as e:
        result["session_id"] = session_id
        result["stored_at"] = None
        result["storage_error"] = str(e)

    # Echo the piece's bar boxes back at the top level so a caller that just
    # sent them (or a frontend rendering the whole page) has every bar's
    # pixel rectangle in hand, not only the bars a finding landed in. `[]`
    # when none were sent.
    result["bar_boxes"] = bar_boxes or []

    return JsonResponse(result)


def _storage_path(path) -> str:
    return str(Path("storage") / Path(path).relative_to(settings.STORAGE_ROOT))


@csrf_exempt
@require_http_methods(["POST"])
def summary_feedback_view(request):
    """POST /api/feedback/summary — phase 2: summarize a whole practice
    session.

    Reads back every Phase1/Phrase<n>.json of `session_id`, aggregates the
    judges' per-phrase scores, ranks the recurring problems
    (feedback_generator.summarizer), and runs the phase-2-only judges
    (feedback_generator/judges/phase2/era.py, which needs piece.composed_date --
    stored with the phrases in phase 1, or overridden by `piece` here).

    Writes one file per phase-2 judge into
    storage/feedback/<session_id>/Phase2/ (Summary.json, Era.json) and
    returns them. Re-runnable: each run overwrites Phase2 with a snapshot of
    every phrase judged so far.

    Body: {"session_id": str, "piece": {...} (optional override)}
    Response: {"session_id", "phrases": [n, ...], "stored_at": {name: path},
               "phase2": {"Summary": {...}, "Era": {...}}}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    session_id = body.get("session_id")
    piece = body.get("piece")

    if piece is not None and not isinstance(piece, dict):
        return JsonResponse({"error": "piece must be an object"}, status=400)
    try:
        feedback_store.validate_session_id(session_id)
    except InvalidSessionId as e:
        return JsonResponse({"error": str(e)}, status=400)

    try:
        phrases = feedback_store.load_phrases(settings.STORAGE_ROOT, session_id)
    except StorageFailed as e:
        return JsonResponse({"error": str(e)}, status=500)
    if not phrases:
        return JsonResponse({"error": f"no phase-1 phrases stored for session {session_id}"}, status=404)

    try:
        phase2 = judge_piece(phrases, piece=piece or feedback_store.load_piece(phrases))
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    response = {
        "session_id": session_id,
        "phrases": [entry.get("phrase") for entry in phrases],
        "phase2": phase2,
    }
    try:
        written = feedback_store.save_phase2(settings.STORAGE_ROOT, session_id, phase2)
        response["stored_at"] = {name: _storage_path(path) for name, path in written.items()}
    except (StorageFailed, OSError) as e:
        response["stored_at"] = None
        response["storage_error"] = str(e)

    return JsonResponse(response)
