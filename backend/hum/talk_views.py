"""Talk mode over HTTP: change the song by typing or saying what you want ("make it faster").

POST /api/hum/talk              JSON {text, settings?, previous?, character?}  (typed)
                                or multipart `audio` + `state` (JSON: {settings, previous, character})  (spoken)
                                -> what was heard, the intent, the new settings, and a reply to show
                                and speak: {heard, intent, settings, changed, understood, reply, error,
                                speech_id}. `previous` is the settings before the last change, so
                                "undo" can be said.
GET  /api/hum/talk/speech/<id>  that reply spoken, streamed as MP3

Gemini works out what was asked and ElevenLabs hears and speaks it. Their keys (GEMINI_API_KEY,
ELEVENLABS_API_KEY) come from backend/.env; a missing key gives a plain message here, not a crash.
The words-to-settings logic itself is in hum/engine/talk/.
"""

import json
import logging
import threading

from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hum.engine.talk.characters import Character, character
from hum.engine.talk.config import load_config
from hum.engine.talk.services import Services, build_services
from hum.engine.talk.settings import SongSettings
from hum.engine.talk.tts import AUDIO_MIME
from hum.views import error, read_json

log = logging.getLogger(__name__)

_services: Services | None = None
_services_lock = threading.Lock()


def get_services() -> Services:
    """Built on first use, so the server (and its tests) start without the API keys."""
    global _services
    with _services_lock:
        if _services is None:
            _services = build_services(load_config())
        return _services


def reset_services(services: Services | None = None) -> None:
    """Replaces the services (tests hand in fakes) or clears them so the keys are read again."""
    global _services
    with _services_lock:
        _services = services


@csrf_exempt
@require_POST
def talk(request: HttpRequest):
    audio = request.FILES.get("audio")
    try:
        if audio is not None:
            state = json.loads(request.POST.get("state") or "{}")
            text = None
        else:
            state = read_json(request)
            if state is None or not isinstance(state.get("text"), str):
                return error("Send JSON {text} or a recording in a form field called audio.", 400, "bad_request")
            text = state["text"]
        current, previous, gnome = _read_state(state)
    except (ValueError, json.JSONDecodeError) as exc:
        return error(str(exc) or "That request didn't make sense.", 400, "bad_request")

    services = get_services()
    if audio is not None:
        turn = services.pipeline.from_audio(audio.read(), audio.name or "talk.wav", current, previous, gnome.personality)
    else:
        turn = services.pipeline.from_text(text, current, previous, gnome.personality)
    # the reply is spoken later, in this character's voice
    speech_id = services.replies.put((turn.reply, gnome.voice_id))
    return JsonResponse({**turn.to_dict(), "speech_id": speech_id})


@require_GET
def speech(request: HttpRequest, reply_id: str):
    services = get_services()
    saved = services.replies.get(reply_id)
    if saved is None:
        return error("That reply has expired. Say it again.", 404, "expired")
    text, voice_id = saved
    try:
        chunks = iter(services.speak(text, voice_id))
        first = next(chunks, b"")  # fail here, before any audio is sent, if the voice service is down
    except Exception as exc:  # noqa: BLE001 - answered as "voice unavailable"
        log.exception("text to speech failed")
        return error(f"The voice isn't available right now ({type(exc).__name__}).", 503, "voice_unavailable")
    return StreamingHttpResponse(_first_then_rest(first, chunks), content_type=AUDIO_MIME, headers={"Cache-Control": "no-store"})


def _first_then_rest(first: bytes, rest):
    yield first
    yield from rest


def _read_state(data) -> tuple[SongSettings, SongSettings | None, Character]:
    """The settings the app has now, the version before them (so "undo" can be said), and the
    character's personality (ECKO when none or an unknown one is named). Raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError("state must be an object")
    previous = data.get("previous")
    current = SongSettings.from_dict(data.get("settings"))
    return current, SongSettings.from_dict(previous) if previous else None, character(data.get("character"))
