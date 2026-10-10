# Backend hosting: Option B (Google Cloud Run, stateless, object storage)

- **Status:** Hosting option **B is chosen** (2026-10-10). The sections after "Decision" are a proposal that still needs review.
- **Based on:** `origin/main` @ `284faec6` (the code after the hum, scores/PDMX and R2 commits). The earlier IMSLP/Playwright backend no longer exists there.
- **Scope:** getting `backend/` running on a cheap, reliable cloud host so the iOS app (App Store build) can reach it over HTTPS. The Rust engine (`native_ffi`) runs on the phone and is not part of this.

## Decision

Run the Django backend as a **stateless container on Google Cloud Run**, with:

| Concern | Choice | Why |
|---|---|---|
| Compute | Cloud Run, scale to zero | Pays only while handling requests; near $0 at low traffic. |
| Database | Managed Postgres (see Open decisions) | Django already uses Postgres; the container must not hold data. |
| Files | Object storage (Cloudflare R2, S3-compatible) | The repo already uses R2 for the PDMX MusicXML tree (`PDMX_MXL_BASE_URL`), and `boto3` is already a dependency. |
| TLS | Provided by Cloud Run | iOS App Transport Security needs `https://`. |

**Why "stateless" is the core constraint.** Cloud Run may run zero, one or many copies of the container, and each copy has its own temporary disk that is wiped when it stops. Any request that expects a file written by an earlier request will fail whenever it lands on a different copy, or after the copy is recycled. Everything below follows from that.

Rejected: **A (Fly.io)** and **C (Render/Railway)**. They allow keeping local disk, but give up scale-to-zero and a cheaper long-term bill.

## Can it run in production today?

**No, not as it stands.** The app logic works locally, but nothing is packaged for the cloud and several features depend on local disk. The blockers, most severe first:

### Must fix before the first public deploy

1. **Hum flow keeps state on local disk and in memory.** `POST /api/hum/upload` saves the WAV under `HUM_DATA_DIR/uploads` and returns a `filename`; `/api/hum/song`, `/notes`, `/raw*` and `/project*` then look that file up by name (`hum/paths.py`, `hum/views.py`). Intermediate files go to `runs/`, `transcriptions/` and `stems/` in the same directory. Talk-mode replies are held in an in-memory store (`services.replies`, `hum/talk_views.py`) and served by `GET /api/hum/talk/speech/<id>`. On Cloud Run, a second request can reach a different copy and get `404 hum_gone`.
2. **Score MusicXML is read from local disk.** `scores/views.py` serves `STORAGE_ROOT/<musicxml_path>`. That folder is gitignored and filled by `manage.py import_pdmx`, so a fresh container has none of it.
3. **No authentication or rate limiting.** Every route is `csrf_exempt` and public. Hum routes use CPU, and talk mode calls paid Gemini and ElevenLabs APIs, so an open URL is a direct cost risk.
4. **Unsafe defaults in `server/settings.py`.** `DEBUG` defaults to `True`, `SECRET_KEY` has an insecure fallback, `ALLOWED_HOSTS = ["*"]`, and `/storage/` is served publicly by Django's `serve` (its own comment in `hum/paths.py` notes that everything under `storage/` is served to anyone). There is no `SECURE_PROXY_SSL_HEADER` for running behind Cloud Run's proxy.
5. **No container.** There is no `Dockerfile`, `.dockerignore` or WSGI server (gunicorn) in the repo. The image also needs the system `fluidsynth` binary and a General MIDI soundfont (`FluidR3_GM.sf2`, 148 MB, gitignored). `render.py` already looks in `/usr/share/sounds/sf2/`, so the Debian soundfont package may cover this (to be verified in a build). `basic-pitch` must be installed with `--no-deps`.
6. **Quiz route is not wired.** `quiz/urls.py` exists but is never included in `api/urls.py` (`CHANGES.md` item 2). The app calls `/api/quiz/generate`, so it returns 404.
7. **The app can only find the server over mDNS on the LAN** (`ServerDiscovery.dart`, `http://`). It needs a configured `https://` base URL in release builds. Both `ApiClient` and `ScoreRepository` go through `ServerDiscovery.resolveBaseUrl`, so this should be a small, central change.

### Should fix

- **Dependencies:** `requirements.txt` still lists the retired OMR stack (`oemer`, OpenCV, `pyvips`, `pytesseract`, `pdfplumber`) and `zeroconf`. The live routes no longer import `pdf_processor`, so a slim `requirements-prod.txt` can drop them. `requirements.txt` and `pyproject.toml` also disagree.
- **Python 3.13 compatibility** of `librosa`, `onnxruntime`, `pedalboard`, `arvo` and `basic-pitch` has not been checked. The first task is to build the image and run the hum tests inside it.
- **Soundfont setting mismatch:** `.env.example` and the hum README mention `SOUNDFONT_PATH` / `ECKO_SOUNDFONT`, but the code reads only `ECKO_SOUNDFONT`. `SOUNDFONT_PATH` is ignored.
- **Upload size:** `MAX_UPLOAD_BYTES` is 50 MB, but Cloud Run limits HTTP/1 request bodies to roughly 32 MiB (verify). Typical hums are far smaller.
- **Latency:** song rendering is CPU-heavy and Cloud Run adds cold starts. The app's default 30 s client timeout may be too short.
- **Repo size:** `backend/services/music_src/pdmx.db` (71 MB) and `db.sqlite3` are tracked in git; the runtime does not need `pdmx.db` once scores are in Postgres. Exclude them in `.dockerignore`.
- **Housekeeping:** `services/music_src/pdmx.py` has unreachable code after `return local_path`; `backend/Stucture.md` and `backend/api/README.md` still describe IMSLP routes that were removed.

## Proposed approach (needs review)

### Phase 1: Make the server production-safe (settings, wiring)
- Read `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS` and database settings from the environment; default to safe values. Add `SECURE_PROXY_SSL_HEADER`.
- Add gunicorn; serve `/storage/` only in development.
- Wire `quiz.urls` into `api/urls.py`.
- Add a simple API-key check (shared secret header) and per-client rate limiting on the hum and talk routes.
- Add `requirements-prod.txt`.

### Phase 2: Move state off local disk
- Store hum uploads and derived files in R2 (or make each request self-contained), and keep talk replies in a shared place or return the audio inline.
- Serve `musicxml` from R2 (stream it, or redirect to a public or signed URL).
- Keep a storage seam (one small module) so local disk still works in development.

### Phase 3: Package and deploy
- `Dockerfile` (Python 3.13 slim, `fluidsynth`, soundfont, `basic-pitch --no-deps`), `.dockerignore`.
- Cloud Run service with a **max-instances cap**, a memory/CPU size set from measurement, secrets for the Gemini/ElevenLabs/DB/R2 keys, and a budget alert.
- Run `migrate` and `import_pdmx` once against the production database.

### Phase 4: App changes (separate review)
- Configured `https://` base URL in release builds, longer timeouts for song requests, remove `NSLocalNetworkUsageDescription` / Bonjour entries if no longer needed.

### Interim option for a first deploy
If Phase 2 takes longer than expected, set **min and max instances to 1**. One long-lived copy keeps its disk and memory between requests, so the hum flow works, but data is lost on every restart or redeploy and the service no longer scales to zero.

## Open decisions (waiting for the project owner)

1. **Postgres host.** Neon free tier (cheapest; compute wakes after idle) vs Cloud SQL (about $10+/month, always on, same cloud). *Recommendation:* Neon to start.
2. **Hum state.** Move to R2 (Phase 2, robust) vs the single-instance interim (fast, fragile). *Recommendation:* R2, with the interim only as a stopgap.
3. **Object storage.** R2 (already used by the repo) vs Google Cloud Storage (same cloud as compute). *Recommendation:* R2.
4. **Authentication.** Shared app key (stops casual abuse, but can be extracted from the app) vs real per-user accounts (more work, stronger). *Recommendation:* shared key plus rate limits for the first release.

## Not verified yet

- All cloud prices and free-tier limits above are from memory and must be checked before committing.
- I have not built the image, so system packages, Python 3.13 wheels and memory needs are untested.
- I have not read `import_pdmx` or the talk-mode code in full.

## Affects the App Store submission (later)

- The app uploads users' voice recordings to this server and to Gemini and ElevenLabs. The App Privacy labels and a privacy policy URL must say so.
- Release builds must use HTTPS only (ATS).
