"""Change the song by typing or saying it, and edit the project directly. See hum/chat/.

POST /api/hum/chat               JSON {text, project, can_undo?, can_redo?}  (typed)
                                 or multipart `audio` + `state` (JSON {project, can_undo?, can_redo?})  (spoken)
                                 -> {heard, intent, reply, project, changed, mixed, label, error, speech_id}.
                                 `project` is the edited song, or null when nothing changed; `changed`
                                 names the tracks whose sound changed (the only ones rendered again).
                                 intent undo / redo leaves the song to the app, which keeps the history.
GET  /api/hum/chat/speech/<id>   that reply spoken, streamed as MP3
POST /api/hum/project/edit       JSON {project, edits: [Edit]} -> {project, changed, mixed, label, refused}:
                                 the same edits without Gemini, for the app's own controls
POST /api/hum/project/notes      JSON {project} -> {sung, played}: the hum and the song's melody, for the graph

Gemini works out the edits, ElevenLabs hears and speaks; their keys come from backend/.env.
"""

import json
import logging
import threading

from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from pydantic import TypeAdapter, ValidationError

from hum import band, paths
from hum.chat.commands import MAX_EDITS, Edit
from hum.chat.executor import apply
from hum.chat.services import ChatServices, build_chat_services
from hum.engine.audio.errors import PipelineError
from hum.engine.talk.config import load_config
from hum.engine.talk.tts import AUDIO_MIME
from hum.song import Project
from hum.views import HUM_GONE, error, read_json

log = logging.getLogger(__name__)
EDITS = TypeAdapter(list[Edit])

_services: ChatServices | None = None
_services_lock = threading.Lock()


def get_services() -> ChatServices:
    """Built on first use, so the server (and its tests) start without the API keys."""
    global _services
    with _services_lock:
        if _services is None:
            _services = build_chat_services(load_config())
        return _services


def reset_services(services: ChatServices | None = None) -> None:
    """Replaces the services (tests hand in fakes) or clears them so the keys are read again."""
    global _services
    with _services_lock:
        _services = services


@csrf_exempt
@require_POST
def chat(request: HttpRequest):
    audio = request.FILES.get("audio")
    try:
        if audio is not None:
            state = json.loads(request.POST.get("state") or "{}")
        else:
            state = read_json(request)
            if state is None or not isinstance(state.get("text"), str):
                return error("Send JSON {text, project} or a recording in a form field called audio.", 400, "bad_request")
        if not isinstance(state, dict) or not isinstance(state.get("project"), dict):
            return error("Send the song project with the message.", 400, "bad_request")
        project = Project.from_json(state["project"])
    except (ValueError, json.JSONDecodeError) as exc:
        return error(str(exc) or "That request didn't make sense.", 400, "bad_project")

    can_undo, can_redo = bool(state.get("can_undo", True)), bool(state.get("can_redo", True))
    services = get_services()
    if audio is not None:
        turn = services.pipeline.from_audio(audio.read(), audio.name or "chat.wav", project, can_undo, can_redo)
    else:
        turn = services.pipeline.from_text(state["text"], project, can_undo, can_redo)
    speech_id = services.replies.put(turn.reply)
    return JsonResponse({**turn.to_dict(), "speech_id": speech_id})


@require_GET
def speech(request: HttpRequest, reply_id: str):
    services = get_services()
    text = services.replies.get(reply_id)
    if text is None:
        return error("That reply has expired.", 404, "expired")
    try:
        chunks = iter(services.speak(text))
        first = next(chunks, b"")  # fail here, before any audio is sent, if the voice service is down
    except Exception as exc:  # noqa: BLE001 - answered as "voice unavailable"; the app shows the text
        log.exception("text to speech failed")
        return error(f"The voice isn't available right now ({type(exc).__name__}).", 503, "voice_unavailable")
    return StreamingHttpResponse(_first_then_rest(first, chunks), content_type=AUDIO_MIME, headers={"Cache-Control": "no-store"})


def _first_then_rest(first: bytes, rest):
    yield first
    yield from rest


@csrf_exempt
@require_POST
def edit(request: HttpRequest):
    data = read_json(request)
    if data is None or not isinstance(data.get("project"), dict) or not isinstance(data.get("edits"), list):
        return error("Send JSON {project, edits}.", 400, "bad_request")
    if len(data["edits"]) > MAX_EDITS:
        return error(f"At most {MAX_EDITS} edits at a time.", 400, "bad_request")
    try:
        project = Project.from_json(data["project"])
        edits = EDITS.validate_python(data["edits"])
    except ValidationError as exc:
        return error(f"Those edits aren't ones I know ({exc.error_count()} problems).", 400, "bad_edits")
    except ValueError as exc:
        return error(str(exc), 400, "bad_project")
    result = apply(project, edits)
    return JsonResponse({
        "project": result.project.to_json(), "changed": result.changed, "mixed": result.mixed,
        "label": result.label, "refused": result.refused,
    })


@csrf_exempt
@require_POST
def notes(request: HttpRequest):
    data = read_json(request)
    if data is None or not isinstance(data.get("project"), dict):
        return error("Send JSON {project}.", 400, "bad_request")
    try:
        project = Project.from_json(data["project"])
    except ValueError as exc:
        return error(str(exc), 400, "bad_project")
    hum = paths.saved_hum(project.hum or "")
    if hum is None:
        return error(HUM_GONE, 404, "hum_gone")
    try:
        return JsonResponse(band.notes_for_graph(hum, project))
    except PipelineError as exc:
        return error(exc.message, 400, exc.code)
