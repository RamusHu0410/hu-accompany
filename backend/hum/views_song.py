"""The band engine's song project over HTTP. Mounted at /api/hum/project (see hum/urls.py).

POST /api/hum/project        JSON {hum, settings?} -> {project}: the hum arranged as an editable project
                             (hum/song/project.py), with the same settings /api/hum/song takes.
POST /api/hum/project/audio  JSON {project} -> the project mixed as WAV. Only the tracks whose notes,
                             instrument or tempo changed are rendered again; the X-Rendered-Tracks
                             header names them.
POST /api/hum/project/midi   JSON {project} -> every track as one .mid file (attachment).
GET  /api/hum/presets        the genres (with their band) and the moods.
"""

import logging

import pretty_midi
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hum import band, paths
from hum.engine.audio.errors import PipelineError
from hum.rawplay import RenderUnavailable
from hum.song import Project, export_midi
from hum.song.presets import DEFAULT_MOOD, DEFAULT_PRESET, MOODS, PRESETS
from hum.views import HUM_GONE, RECORDING_CODES, error, read_json

log = logging.getLogger(__name__)
CANT_PLAY = "This server can't play sound right now (FluidSynth or a soundfont is missing)."


@csrf_exempt
@require_POST
def project(request: HttpRequest):
    data = read_json(request)
    if data is None or not isinstance(data.get("hum"), str):
        return error("Send JSON with the hum's filename from /api/hum/upload.", 400, "bad_request")
    hum = paths.saved_hum(data["hum"])
    if hum is None:
        return error(HUM_GONE, 404, "hum_gone")
    try:
        arranged = band.project_for(hum, data.get("settings"))
    except ValueError as exc:
        return error(str(exc), 400, "bad_settings")
    except PipelineError as exc:
        status = 400 if exc.code in RECORDING_CODES else 503
        return error(exc.message, status, exc.code)
    return JsonResponse({"project": arranged.to_json()})


def _sent_project(request: HttpRequest) -> tuple[Project | None, JsonResponse | None]:
    data = read_json(request)
    if data is None or not isinstance(data.get("project"), dict):
        return None, error("Send JSON with the song project.", 400, "bad_request")
    try:
        return Project.from_json(data["project"]), None
    except ValueError as exc:
        return None, error(str(exc), 400, "bad_project")


@csrf_exempt
@require_POST
def project_audio(request: HttpRequest):
    sent, failed = _sent_project(request)
    if failed:
        return failed
    try:
        mixed = band.render(sent)
    except RenderUnavailable as exc:
        log.error("project render unavailable: %s", exc)
        return error(CANT_PLAY, 503, "render_unavailable")
    return HttpResponse(mixed.wav, content_type="audio/wav",
                        headers={"Cache-Control": "no-store", "X-Rendered-Tracks": ",".join(mixed.rendered)})


@csrf_exempt
@require_POST
def project_midi(request: HttpRequest):
    sent, failed = _sent_project(request)
    if failed:
        return failed
    return HttpResponse(export_midi(sent), content_type="audio/midi",
                        headers={"Content-Disposition": 'attachment; filename="song.mid"'})


@require_GET
def presets(request: HttpRequest):
    def instrument(program: int | None) -> str | None:
        return None if program is None else pretty_midi.program_to_instrument_name(program)

    return JsonResponse({
        "presets": [
            {
                "id": p.id, "label": p.label, "tempo_range": list(p.tempo_range),
                "band": {"melody": instrument(p.palette.melody), "chords": instrument(p.palette.chords),
                         "bass": instrument(p.palette.bass), "pad": instrument(p.palette.pad)},
            }
            for p in PRESETS.values()
        ],
        "moods": [{"id": m.id, "label": m.label} for m in MOODS.values()],
        "default_preset": DEFAULT_PRESET,
        "default_mood": DEFAULT_MOOD,
    })
