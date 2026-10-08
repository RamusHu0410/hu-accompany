from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import FileResponse, HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from scores.models import Score

DEFAULT_LIMIT = 25
MAX_LIMIT = 50


@require_GET
def search_view(request: HttpRequest):
    """GET /api/scores/search?q=<text>&limit=<n> -- scores whose title or
    composer contains every word of `q`, best-rated first.

    Response: {"query": str, "results": [Score.as_summary(), ...]}
    400 if `q` is blank.
    """
    query = (request.GET.get("q") or "").strip()
    if not query:
        return JsonResponse({"error": "q is required"}, status=400)

    try:
        limit = int(request.GET.get("limit", DEFAULT_LIMIT))
    except ValueError:
        return JsonResponse({"error": "limit must be an integer"}, status=400)
    limit = max(1, min(limit, MAX_LIMIT))

    scores = Score.objects.all()
    for word in query.split():
        scores = scores.filter(Q(title__icontains=word) | Q(composer__icontains=word))

    return JsonResponse({
        "query": query,
        "results": [score.as_summary() for score in scores[:limit]],
    })


@require_GET
def musicxml_view(request: HttpRequest, score_id: int):
    """GET /api/scores/<id>/musicxml -- the score as uncompressed MusicXML.
    404 if the score or its file is missing."""
    score = Score.objects.filter(pk=score_id).first()
    if score is None:
        return JsonResponse({"error": f"score {score_id} not found"}, status=404)

    path = Path(settings.STORAGE_ROOT) / score.musicxml_path
    if not path.is_file():
        return JsonResponse({"error": f"MusicXML for score {score_id} is missing"}, status=404)

    return FileResponse(
        path.open("rb"),
        content_type="application/vnd.recordare.musicxml+xml",
    )
