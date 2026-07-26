# Backend

Django backend for hu-accompany.

## Folder structure

- **`server/`** — Django project configuration (settings, root URL conf, WSGI entry point).
- **`api/`** — Main Django app

- **`imslp_search/`** — IMSLP domain logic: search, parsing, normalization, error types, and the score lookup code (`main.py`).
  - **`imslp_search/services/`** — Service-layer glue code (e.g. `imslp_service.py`) that connects the `imslp_search` logic to the `api` app's models.
- **`imslp_downloader/`** — Django app that handles downloading scores from IMSLP (browser automation, storage, its own API/models/migrations).
- **`scripts/`** — Standalone utility scripts not wired into the Django app (PDF-to-notes processing, note-rating/comparison logic).
- **`storage/`** — Runtime storage for downloaded score files (gitignored).
- **`archive/`** — Old/retired code kept for reference, not part of the running app.
- **`manage.py`** — Django management entry point.
- **`requirements.txt`** — Python dependencies.
- **`db.sqlite3`** — Local SQLite database (gitignored).
- **`.env`** — Local environment variables/secrets (gitignored).
