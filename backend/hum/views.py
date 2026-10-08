"""Hum to song over HTTP, mounted at /api/hum/ (see hum/urls.py). The work lives in hum/engine/.

POST /api/hum/upload   multipart `file` (.wav) -> the tune found in the hum, and `filename` to send
                       back to the other routes. 400 {error, code?} when the recording can't give a tune.
POST /api/hum/song     JSON {hum, settings?, engine?} -> the song as WAV. `hum` is the filename upload
                       returned, `engine` is "band" (default), "epic" or "simple". 404 when the hum is gone,
                       503 when the song couldn't be made on this machine (FluidSynth or a soundfont is missing).
POST /api/hum/notes    the same body -> {sung, played, contour}, in seconds, for drawing the notes.
GET  /api/hum/engines  the engines, and the styles each knows.

The engines make a different kind of song from the same tune: "band" (hum/song) arranges it for a
genre's band as intro, verse, chorus and outro, as an editable song project (see views_song.py);
"epic" is the arrangement pipeline (hum/engine/audio), a full ensemble that works best from a clean hum; "simple" is the chord-and-style accompanist (hum/engine/accompanist, driven by
hum/engine/talk/song.py), steadier on a rough one.
"""

import json
import logging
import os
from functools import lru_cache

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hum import band, paths
from hum.engine.accompanist.music.styles import STYLES as SIMPLE_STYLES
from hum.engine.audio.arrange import arranged_melody
from hum.engine.audio.arrange.config import DEFAULT_STYLE, STYLE_ALIASES, STYLES as EPIC_STYLES
from hum.engine.audio.arrange.ensembles import ENSEMBLES
from hum.engine.audio.arrange.melody import key_tonic_and_mode, load_melody
from hum.engine.audio.errors import PipelineError
from hum.engine.audio.intake import AudioInputError, inspect_wav, unique_upload_name
from hum.engine.audio.pipeline import melody_run_for, new_run_dir, rerun
from hum.engine.talk.settings import SongSettings
from hum.engine.talk.song import SongError, make_song, song_notes
from hum.page_settings import settings_from_page, variation_for
from hum.rawplay import RenderUnavailable
from hum.song.presets import DEFAULT_MOOD, DEFAULT_PRESET, MOODS, PRESETS

log = logging.getLogger(__name__)

ENGINES = ("band", "epic", "simple")
DEFAULT_ENGINE = "band"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
HUM_GONE = "That hum isn't on the server any more. Hum again."
# Refusals caused by the recording itself (the user can fix them by humming again): 400.
# Anything else went wrong on our side: 503.
RECORDING_CODES = {"no_tune", "silent", "too_short", "too_long", "unreadable", "empty", "not_found", "input_changed"}


def error(message: str, status: int, code: str | None = None, **extra) -> JsonResponse:
    body = {"error": message, **extra}
    if code:
        body["code"] = code
    return JsonResponse(body, status=status)


def _failure(exc: PipelineError) -> JsonResponse:
    status = 400 if exc.code in RECORDING_CODES else 503
    if status == 503:
        log.error("pipeline failed at %s (%s): %s", exc.step, exc.code, exc.__cause__ or exc)
    return error(exc.message, status, exc.code, step=exc.step)


def read_json(request: HttpRequest) -> dict | None:
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _hum_request(request: HttpRequest):
    """The parsed body and the saved hum it names, or an error response to send back."""
    data = read_json(request)
    if data is None or not isinstance(data.get("hum"), str):
        return None, None, error("Send JSON with the hum's filename from /api/hum/upload.", 400, "bad_request")
    hum = paths.saved_hum(data["hum"])
    if hum is None:
        return None, None, error(HUM_GONE, 404, "hum_gone")
    engine = data.get("engine", DEFAULT_ENGINE)
    if engine not in ENGINES:
        return None, None, error(f"engine must be one of {', '.join(ENGINES)}.", 400, "bad_request")
    return data, (hum, engine), None


@csrf_exempt
@require_POST
def upload(request: HttpRequest):
    file = request.FILES.get("file")
    if file is None:
        return error("No file part in request", 400, "bad_request")
    if not file.name.lower().endswith((".wav", ".wave")):
        return error("Invalid file type. Only .wav files are allowed.", 400, "bad_request")
    if file.size > MAX_UPLOAD_BYTES:
        return error("That recording is too big.", 413, "too_big")

    filename = unique_upload_name(file.name)
    path = paths.upload_dir() / filename
    with open(path, "wb") as saved:
        for chunk in file.chunks():
            saved.write(chunk)

    try:
        inspect_wav(str(path))  # quick checks first: a readable WAV of a sensible length
        run_dir, warnings = melody_run_for(str(path), paths.runs_dir())
        melody = load_melody(run_dir / "melody.json")
    except AudioInputError as exc:
        path.unlink(missing_ok=True)
        return error(str(exc), 400)
    except PipelineError as exc:
        path.unlink(missing_ok=True)
        if exc.code in RECORDING_CODES:
            return error(exc.message, 400, exc.code)
        log.error("intake failed at %s (%s): %s", exc.step, exc.code, exc.__cause__ or exc)
        return error("Audio processing failed", 500, details=exc.message)
    except Exception as exc:  # noqa: BLE001 - a bug, not a bad file: say so plainly
        log.exception("Audio processing failed")
        path.unlink(missing_ok=True)
        return error("Audio processing failed", 500, details=str(exc))

    tonic, mode = key_tonic_and_mode(melody.key)
    return JsonResponse(
        {
            "status": "success",
            "filename": filename,
            "run_id": run_dir.name,
            # the engine's "hz" holds MIDI note numbers, its times are beats
            "melody": [{"hz": float(n.pitch), "start": n.start_beats, "duration": n.duration_beats} for n in melody.notes],
            "tempo": float(melody.tempo_bpm),
            "key": tonic,
            "mode": mode,
            "tuning_cents": float(melody.tuning_offset_cents),
            "warnings": warnings,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def song(request: HttpRequest):
    data, found, failed = _hum_request(request)
    if failed:
        return failed
    hum, engine = found
    try:
        if engine == "band":
            wav = band.render(band.project_for(hum, data.get("settings"))).wav
        elif engine == "epic":
            wav = _epic_song(hum, data)
        else:
            wav = make_song(str(hum), SongSettings.from_dict(data.get("settings")))
    except ValueError as exc:
        return error(str(exc), 400, "bad_settings")
    except PipelineError as exc:
        return _failure(exc)
    except (SongError, RenderUnavailable) as exc:
        log.error("song failed (%s): %s", engine, exc)
        return error(str(exc), 503, "song_failed")
    return HttpResponse(wav, content_type="audio/wav", headers={"Cache-Control": "no-store"})


def _epic_song(hum, data: dict) -> bytes:
    style, settings = settings_from_page(data.get("settings"), variation=variation_for(hum.name))
    runs = paths.runs_dir()
    # The hum's melody is transcribed once and reused, so a settings change only re-arranges it.
    melody_run, _warnings = melody_run_for(str(hum), runs)
    result = rerun(melody_run, style, "transform", run_dir=str(new_run_dir(runs)), settings=settings)
    return open(result.final_wav_path, "rb").read()


@csrf_exempt
@require_POST
def notes(request: HttpRequest):
    data, found, failed = _hum_request(request)
    if failed:
        return failed
    hum, engine = found
    try:
        if engine == "band":
            return JsonResponse(band.notes_for_graph(hum, band.project_for(hum, data.get("settings"))))
        if engine == "simple":
            return JsonResponse(song_notes(str(hum), SongSettings.from_dict(data.get("settings"))))
        style, settings = settings_from_page(data.get("settings"))
        melody_run, _ = melody_run_for(str(hum), paths.runs_dir())
    except ValueError as exc:
        return error(str(exc), 400, "bad_settings")
    except PipelineError as exc:
        return _failure(exc)
    heard = load_melody(melody_run / "melody.json")
    played, _, _ = arranged_melody(heard, style, settings)
    contour = _contour(str(hum), os.stat(hum).st_mtime_ns)
    # intake trimmed the silence before the hum, and its first note is beat 0: put both tunes where
    # the singing starts
    first = contour["segments"][0]["start"] if contour.get("segments") else 0.0
    return JsonResponse({"sung": _seconds(heard, first), "played": _seconds(played, first), "contour": contour})


def _seconds(melody, first: float) -> list[dict]:
    spb = melody.seconds_per_beat
    return [
        {"midi": n.pitch, "start": round(first + n.start_beats * spb, 3), "duration": round(n.duration_beats * spb, 3)}
        for n in melody.notes
    ]


@lru_cache(maxsize=32)
def _contour(hum_path: str, _changed_at: int) -> dict:
    """The hum's pitch frame by frame, for drawing. Settings changes redraw the graph, so it's kept
    per recording."""
    from hum.engine.audio.processor import analyze_audio_file

    return analyze_audio_file(hum_path).get("contour") or {"step": 0.0, "segments": []}


@require_GET
def engines(request: HttpRequest):
    return JsonResponse(
        {
            "engines": [
                {"id": "band", "name": "Band", "styles": list(PRESETS), "default_style": DEFAULT_PRESET,
                 "moods": list(MOODS), "default_mood": DEFAULT_MOOD},
                {"id": "epic", "name": "Epic", "styles": sorted(EPIC_STYLES), "default_style": DEFAULT_STYLE,
                 "style_aliases": STYLE_ALIASES, "ensembles": sorted(ENSEMBLES)},
                {"id": "simple", "name": "Simple", "styles": sorted(SIMPLE_STYLES)},
            ],
            "default": DEFAULT_ENGINE,
        }
    )
