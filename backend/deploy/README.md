# Production hosting: Google Cloud Run

In production, the Python (Django) backend in `backend/` runs on **Google Cloud Run** as a stateless container. The iOS app reaches it over HTTPS.

> **Status: planned, not deployed yet.** There is no `Dockerfile`, no gunicorn, and the code still relies on local disk in places. This README records the hosting decision and what the code has to satisfy. The detailed analysis and phased plan are in [`docs/superpowers/specs/2026-10-10-backend-cloud-run-deployment-design.md`](../../docs/superpowers/specs/2026-10-10-backend-cloud-run-deployment-design.md).

## Scope

- **In scope:** the Django server in `backend/` (`server/`, `api/`, `scores/`, `hum/`, `quiz/`).
- **Out of scope:** the Rust engine in `native_ffi/`, which runs on the phone, and the Flutter app in `frontend/`.

## Architecture

| Concern | Production choice | Why |
|---|---|---|
| Compute | Cloud Run (container, scales to zero) | Pay only while requests are being handled, so the bill is near $0 at low traffic. |
| Database | Managed Postgres (host undecided, see below) | Django already targets Postgres, and the container must not store data. |
| Files | Object storage, Cloudflare R2 (S3-compatible) | The repo already uses R2 for the PDMX MusicXML tree (`PDMX_MXL_BASE_URL`) and already depends on `boto3`. |
| TLS | Provided by Cloud Run | iOS App Transport Security requires `https://`. |
| Secrets | Cloud Run secrets / environment | Gemini, ElevenLabs, database and R2 keys never live in the image or in git. |

```
iOS app --HTTPS--> Cloud Run (Django + gunicorn) --> Postgres (scores, catalog)
                                |
                                +--> R2 (MusicXML, hum audio)
                                +--> Gemini / ElevenLabs APIs (talk mode)
```

## The key constraint: the container must be stateless

Cloud Run can run zero, one, or many copies of the container at once. Each copy has its own temporary disk, and that disk is wiped when the copy stops. If request B expects a file that request A wrote, it fails whenever B lands on a different copy or after a restart.

So the rule for all backend code is: **nothing a later request needs may live only on the container's disk or in its memory.** Persist it to Postgres or R2 instead.

## What currently breaks that rule

These are the main blockers. Each has to be fixed before the first public deploy (the spec has the complete list).

1. **Hum flow** (`hum/`): uploads, `runs/`, `transcriptions/`, `stems/`, and talk-mode replies are held on local disk or in memory. A follow-up request on a different copy returns `404 hum_gone`.
2. **Score MusicXML** (`scores/views.py`): read from `STORAGE_ROOT`, a gitignored folder filled by `manage.py import_pdmx`. A fresh container has none of it.
3. **No auth or rate limiting:** every route is public, and talk mode calls paid APIs. Needs a shared app key and rate limits.
4. **Unsafe settings defaults** (`server/settings.py`): `DEBUG=True`, an insecure `SECRET_KEY` fallback, `ALLOWED_HOSTS=["*"]`, and `/storage/` served publicly. These must come from the environment and default to safe values.
5. **No container:** the image needs gunicorn, the `fluidsynth` binary, a General MIDI soundfont, and `basic-pitch` installed with `--no-deps`.
6. **Quiz route not wired:** `quiz/urls.py` is never included in `api/urls.py`.

## Deployment plan (summary)

1. **Make the server production-safe:** environment-driven settings, gunicorn, `SECURE_PROXY_SSL_HEADER` (Cloud Run terminates TLS in front of Django), API-key check, rate limits, a slim `requirements-prod.txt`.
2. **Move state off local disk:** hum files and score MusicXML to R2, talk replies to shared storage or returned inline. Keep one small storage module so local disk still works in development.
3. **Package and deploy:** `Dockerfile` and `.dockerignore`, then a Cloud Run service with:
   - a **max-instances cap**, so a traffic spike or abuse can't produce an unbounded bill
   - memory and CPU sized from measurement, because hum rendering is CPU-heavy
   - secrets mounted for the Gemini, ElevenLabs, database and R2 keys
   - a **budget alert**
   - `migrate` and `import_pdmx` run once against the production database
4. **App changes** (separate review): a configured `https://` base URL for release builds (the app currently finds the server over mDNS on the LAN), and longer timeouts for song requests.

**Stopgap if step 2 slips:** set min and max instances to 1. One long-lived copy keeps its disk and memory, so the hum flow works. Data is lost on every restart or redeploy, and the service no longer scales to zero. Use it as a temporary measure only.

## Things to keep in mind

- **Cold starts:** scale-to-zero means the first request after idle is slower. Song rendering is already CPU-heavy, so the app's default 30 s client timeout may be too short.
- **Upload size:** `MAX_UPLOAD_BYTES` is 50 MB, but Cloud Run limits HTTP/1 request bodies to roughly 32 MiB (to be verified). Typical hums are much smaller.
- **Image size:** exclude `db.sqlite3` and `services/music_src/pdmx.db` (71 MB) via `.dockerignore`.
- **Privacy:** the app sends users' voice recordings to this server and on to Gemini and ElevenLabs. The App Store privacy labels and privacy policy must say so.

## Open decisions

| # | Question | Options | Current recommendation |
|---|---|---|---|
| 1 | Postgres host | Neon free tier vs Cloud SQL (about $10+/month, always on) | Neon to start |
| 2 | Hum state | Move to R2 vs single-instance stopgap | R2; stopgap only temporarily |
| 3 | Object storage | R2 (already used) vs Google Cloud Storage | R2 |
| 4 | Authentication | Shared app key + rate limits vs per-user accounts | Shared key + rate limits for the first release |

## Not verified yet

- Cloud prices, free-tier limits and the Cloud Run request-size limit are from memory. Check them against current Google Cloud docs before committing to numbers.
- The image hasn't been built, so the system packages, Python 3.13 wheels (`librosa`, `onnxruntime`, `pedalboard`, `basic-pitch`) and memory needs are untested.
