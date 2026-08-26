import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from imslp_downloader import storage as score_storage
from imslp_search.main import search_imslp
from imslp_search.errors import IMSLPNetworkError, WorkNotFoundError
from imslp_search.services import imslp_service
import pdf_processor


@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
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
def search_view(request):
    client_ip = request.META.get("REMOTE_ADDR")
    try:
        body = json.loads(request.body)
        query = body.get("query", "").strip()
        print(f"[search] request from {client_ip} -> query={query!r}")
        if not query:
            return JsonResponse({"error": "query is required"}, status=400)
        results = search_imslp(query)
        print(f"[search] sending {len(results)} result(s) to {client_ip}: {results}")
        return JsonResponse({"query": query, "results": results})
    except json.JSONDecodeError:
        print(f"[search] invalid JSON from {client_ip}")
        return JsonResponse({"error": "invalid JSON"}, status=400)
    except Exception as e:
        print(f"[search] error for {client_ip}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_score_view(request):
    """POST /api/score/process — run the oemer-based OMR pipeline
    (backend/pdf_processor) on a stored score PDF: clean up scan noise with
    adaptive thresholding + morphology (backend/image_enhancer), split into
    page PNGs, run OMR to MusicXML with a debug PNG per page (every detected
    notehead/clef/barline/accidental/marking/etc. boxed and labeled), then
    parse timed note events into a notes JSON per page (part1_notes) and OCR
    composer markings -- dynamics/tempo/expression/technique/time signature
    -- into a markings JSON per page (part2_markings). All per-page output
    files are written next to the source PDF in storage, plus one combined
    piece_json/piece_data for the whole piece.

    Body: {"file_path": "storage/scores/<Composer>/<Work>/<file>.pdf"}
    `file_path` matches the format returned by /api/imslp/download's file_path.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    file_path = (body.get("file_path") or "").strip()
    if not file_path:
        return JsonResponse({"error": "file_path is required"}, status=400)

    if not score_storage.exists(file_path):
        return JsonResponse({"error": f"file not found: {file_path}"}, status=404)

    pdf_path = score_storage.db_path_to_absolute(file_path)

    try:
        result = pdf_processor.process(str(pdf_path))
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    def to_db_paths(paths):
        return [
            score_storage.to_db_path(Path(p).relative_to(settings.STORAGE_ROOT))
            for p in paths
        ]

    def to_db_path(path):
        return score_storage.to_db_path(Path(path).relative_to(settings.STORAGE_ROOT))

    return JsonResponse({
        "file_path": file_path,
        "enhanced_pdf": to_db_path(result["enhanced_pdf"]),
        "pages": to_db_paths(result["pages"]),
        "musicxml": to_db_paths(result["musicxml"]),
        "debug_png": to_db_paths(result["debug_png"]),
        "notes_json": to_db_paths(result["notes_json"]),
        "markings_json": to_db_paths(result["markings_json"]),
        "markings_debug_png": to_db_paths(result["markings_debug_png"]),
        "piece_json": to_db_path(result["piece_json"]),
        "piece_data": result["piece_data"],
        "bpm": result["bpm"],
        "time_signature": result["time_signature"],
        "note_count": len(result["notes"]),
        "marking_count": len(result["markings"]),
        "timing": result["timing"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def imslp_search_view(request):
    client_ip = request.META.get("REMOTE_ADDR")
    try:
        body = json.loads(request.body)
        query = (body.get("query") or "").strip()
        url = (body.get("url") or "").strip() or None
        if not query and not url:
            return JsonResponse({"error": "query is required"}, status=400)
        print(f"[imslp/search] request from {client_ip} -> query={query!r} url={url!r}")
        result = imslp_service.search(query, url=url)
        return JsonResponse(result)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    except WorkNotFoundError as e:
        return JsonResponse({"error": str(e)}, status=404)
    except IMSLPNetworkError as e:
        return JsonResponse({"error": str(e)}, status=502)
    except Exception as e:
        print(f"[imslp/search] error for {client_ip}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
