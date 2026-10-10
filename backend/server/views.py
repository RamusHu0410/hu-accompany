from django.conf import settings
from django.http import Http404
from django.views.static import serve


def storage(request, path):
    """Serves files under backend/storage/ by URL, for local development only.

    It has no per-file access check, and storage/ holds feedback files, so on a
    server that is open to the internet it must not answer. `DEBUG` is False
    in production (see server/config.py), which turns this into a 404. The app
    reads scores through /api/scores/<id>/musicxml, not through here.
    """
    if not settings.DEBUG:
        raise Http404("storage is not served")
    return serve(request, path, document_root=settings.BASE_DIR / "storage")
