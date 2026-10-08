# Backend

Django backend for hu-accompany.

## Folder structure

- **`server/`** — Django project configuration (`settings.py`, root URL conf `urls.py`, `wsgi.py` entry point). Registers the `api`, `scores`, and `hum` apps and the PostgreSQL + storage settings.

- **`api/`** — Main Django app: the HTTP routes for IMSLP search/download and score processing (`views.py`, `urls.py`), plus `models.py`, `mdns.py`, and `migrations/`. See `api/README.md` for the full route list.

- **`scores/`** — Django app for the local score catalog built from the PDMX dataset: catalog reads (`catalog.py`), MusicXML parsing (`musicxml.py`), search views (`views.py`, `urls.py`), models, migrations, and import management commands.

- **`hum/`** — Django app ported from the ECKO Flask backend: a user hums a tune and gets back a generated song, reshapeable by typing or speaking. HTTP layer (`views.py`, `talk_views.py`, `urls.py`) over the framework-free `engine/` (audio intake, the epic/simple arrangement engines, and Gemini/ElevenLabs talk mode). See `hum/README.md`.

- **`imslp_search/`** — IMSLP domain logic: search, parsing, normalization, error types, and the score lookup code (`main.py`, `search.py`, `parser.py`, `normalizer.py`, `models.py`, `errors.py`).

  - **`imslp_search/services/`** — Service-layer glue that connects the `imslp_search` logic to the `api` app's models.

- **`imslp_downloader/`** — Django app that downloads scores from IMSLP (browser automation through the disclaimer/subscribe flow), with its own `management/` commands and `migrations/`.

- **`pdf_processor/`** — The oemer ML-based OMR pipeline: `part1_notes/` (PDF → PNG → MusicXML → timed notes) and `part2_markings/` (OCR of composer markings), driven by the `pdf_to_notes.py` entry point. See `pdf_processor/README.md`.

- **`image_enhancer/`** — Standalone libvips-based script (`enhancer_script.py`) that cleans and sharpens scanned score PDFs page by page before OMR.

- **`feedback_generator/`** — Two-phase performance feedback: phase 1 judges one phrase at a time, phase 2 summarizes the session. Judges in `judges/`, score-highlight boxes in `bar_boxes/`, storage glue in `store.py`/`summarizer.py`. See `feedback_generator/README.md`.

- **`quiz/`** — Framework-light music theory/history quiz generator driven by a typed topic heading; hand-written question `banks/`, topic parsing, and category-balanced draw with thin Django views. See `quiz/README.md`.

- **`services/`** — Catalog-building helpers outside the Django apps.
  - **`services/music_src/`** — PDMX catalog ingestion (`pdmx.py`, `openscore.py`) and the local `pdmx.db` SQLite catalog read by the `scores` app.

- **`db/`** — Legacy SQLAlchemy scaffold (`db.py`, `models.py`, `crud.py`, `schemas.py`) kept for the catalog-import code path; the live schema is managed with the Django ORM. See `db/README.md`.

- **`storage/`** — Runtime file storage (gitignored contents): `scores/` (downloaded/enhanced PDFs and rendered PNGs) and `feedback/` (feedback JSON sessions). The DB stores only paths into here. See `storage/README.md`.

- **`archive/`** — Old/retired code kept for reference (`Converter/`, an earlier `image_processor_*/`, legacy `scripts/`), not part of the running app.

- **`manage.py`** — Django management entry point.

- **`docker-compose.yml`** — Local PostgreSQL (and MinIO) services for development.

- **`pyproject.toml`** / **`uv.lock`** — Project metadata and the locked dependency set (managed with `uv`).

- **`requirements.txt`** — Pinned Python dependencies for `pip`-based installs.

- **`pytest.ini`** — Pytest config for the framework-free `hum/` engine tests.

- **`db.sqlite3`** — Local SQLite database (gitignored).

- **`.env`** / **`.env.example`** — Local environment variables/secrets (`.env` is gitignored) and the committed template.
