"""Handles POST /api/imslp/download (Phase 2 of the design doc)."""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import downloader
from .exceptions import (
    BrowserError,
    DownloadFailed,
    FileSaveFailed,
    InvalidIMSLPURL,
    SubscriptionRequired,
)
from .models import DownloadResponse


@csrf_exempt
@require_http_methods(["POST"])
def download_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    score_id = str(body.get("score_id") or "").strip()
    imslp_url = (body.get("imslp_url") or "").strip()
    if not score_id:
        return JsonResponse({"error": "score_id is required"}, status=400)

    existing = downloader.find_existing(score_id)
    if existing:
        return JsonResponse(
            DownloadResponse(
                status="completed", score_id=score_id, file_path=existing.file_path
            ).to_dict()
        )

    try:
        record = downloader.download(score_id, imslp_url)
    except InvalidIMSLPURL as exc:
        return JsonResponse(
            DownloadResponse(status="failed", score_id=score_id, error=str(exc)).to_dict(),
            status=400,
        )
    except SubscriptionRequired as exc:
        # Not a transient network/browser problem -- IMSLP's own file host
        # has capped free downloads from this IP for now. Distinct status so
        # the client can tell "try again later" apart from "IMSLP is down".
        return JsonResponse(
            DownloadResponse(status="failed", score_id=score_id, error=str(exc)).to_dict(),
            status=503,
        )
    except (BrowserError, DownloadFailed) as exc:
        return JsonResponse(
            DownloadResponse(status="failed", score_id=score_id, error=str(exc)).to_dict(),
            status=502,
        )
    except FileSaveFailed as exc:
        return JsonResponse(
            DownloadResponse(status="failed", score_id=score_id, error=str(exc)).to_dict(),
            status=500,
        )

    return JsonResponse(
        DownloadResponse(
            status="completed", score_id=score_id, file_path=record.file_path
        ).to_dict()
    )
