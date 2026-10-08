"""Your hum, as hummed. Mounted at /api/hum/raw (see hum/urls.py).

POST /api/hum/raw         JSON {hum} -> the raw notes (what was hummed: pitch, onset and duration in
                          seconds from the first note, velocity), the tempo and key, and `quantized`,
                          the same tune on the beat grid and inside the key, which arrangements use.
POST /api/hum/raw/audio   JSON {hum, instrument?} -> the raw notes played exactly, as WAV.
                          `instrument` is "piano" (default) or "synth".
POST /api/hum/raw/midi    JSON {hum} -> the raw notes as a .mid file (attachment).

The notes come from hum/transcription.py and the sound from hum/rawplay.py; this only carries them.
"""

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from hum import paths, rawplay
from hum.engine.audio.errors import PipelineError
from hum.transcription import Transcription, transcription_for
from hum.views import HUM_GONE, RECORDING_CODES, error, read_json

log = logging.getLogger(__name__)


def _transcription(request: HttpRequest) -> tuple[dict | None, Transcription | None, JsonResponse | None]:
    """The request body, the hum's transcription, or an error response to send instead."""
    data = read_json(request)
    if data is None or not isinstance(data.get("hum"), str):
        return None, None, error("Send JSON with the hum's filename from /api/hum/upload.", 400, "bad_request")
    hum = paths.saved_hum(data["hum"])
    if hum is None:
        return None, None, error(HUM_GONE, 404, "hum_gone")
    try:
        return data, transcription_for(hum, paths.data_dir() / "transcriptions"), None
    except PipelineError as exc:
        status = 400 if exc.code in RECORDING_CODES else 503
        if status == 503:
            log.error("transcription failed (%s): %s", exc.code, exc.__cause__ or exc)
        return None, None, error(exc.message, status, exc.code)


@csrf_exempt
@require_POST
def raw_notes(request: HttpRequest):
    _, transcription, failed = _transcription(request)
    if failed:
        return failed
    return JsonResponse(
        {
            "notes": [
                {"midi": n.pitch, "start": n.start, "duration": n.duration, "velocity": n.velocity}
                for n in transcription.raw
            ],
            "quantized": [
                {"midi": n.pitch, "start": n.start, "duration": n.duration, "velocity": n.velocity}
                for n in transcription.quantized()
            ],
            "tempo": transcription.tempo_bpm,
            "key": transcription.tonic,
            "mode": transcription.mode,
            "tuning_cents": transcription.tuning_cents,
            "duration": transcription.duration,
            "warnings": transcription.warnings,
        }
    )


@csrf_exempt
@require_POST
def raw_audio(request: HttpRequest):
    data, transcription, failed = _transcription(request)
    if failed:
        return failed
    try:
        wav = rawplay.render_raw(transcription, data.get("instrument", rawplay.DEFAULT_INSTRUMENT))
    except ValueError as exc:
        return error(str(exc), 400, "bad_request")
    except rawplay.RenderUnavailable as exc:
        log.error("raw playback unavailable: %s", exc)
        return error("This server can't play sound right now (FluidSynth or a soundfont is missing).", 503, "render_unavailable")
    return HttpResponse(wav, content_type="audio/wav", headers={"Cache-Control": "no-store"})


@csrf_exempt
@require_POST
def raw_midi(request: HttpRequest):
    _, transcription, failed = _transcription(request)
    if failed:
        return failed
    return HttpResponse(
        rawplay.export_midi(transcription),
        content_type="audio/midi",
        headers={"Content-Disposition": 'attachment; filename="hum.mid"'},
    )
