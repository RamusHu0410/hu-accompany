# Database

PostgreSQL is the single source of truth for all structured data in the
backend: IMSLP works/versions, download records, and the OMR pipeline's
output (per-piece `piece_data` and `bar_boxes`, per-page MusicXML, notes and
markings). It does **not** store large binary media — the score PDFs, the
enhanced PDFs, and the rendered page/debug PNGs stay on disk under
`backend/storage/`, and the database keeps only their `storage/...` paths.

The schema is managed with the **Django ORM** (models in `api/models.py` and
`imslp_downloader/models.py`), not raw SQLAlchemy. The previous SQLAlchemy
scaffold that lived in this folder (`db.py`, `models.py`, `crud.py`,
`schemas.py`) has been removed in favor of a single ORM.

## Prerequisites

- Docker Desktop (or Docker Engine with Compose)
- Python 3.13+ with the backend dependencies installed
  (`pip install -r requirements.txt`) — this includes `psycopg[binary]`, the
  PostgreSQL driver Django uses.

## Start PostgreSQL locally

From `backend/`, start the PostgreSQL service:

```bash
docker compose up -d
```

Check that it is running / stop it:

```bash
docker compose ps
docker compose down          # keeps the data volume
```

Do not run `docker compose down -v` unless you intentionally want to delete
all local database data.

## Configuration

Django reads the connection settings from environment variables (see
`backend/.env`), with defaults that match the `postgres` service in
`docker-compose.yml`:

```env
POSTGRES_DB=music_catalog
POSTGRES_USER=app
POSTGRES_PASSWORD=local_dev_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

Use the host address `localhost` when connecting from Python on your machine.
Use the Docker service name `postgres` only when another Docker container
needs to connect.

## Create / update the schema

Migrations are Django migrations. From `backend/`:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Access the database directly

```bash
docker compose exec postgres psql -U app -d music_catalog
```

Useful `psql` commands:

```sql
\dt                         -- list tables
\d api_processedscore       -- describe a table
\q                          -- quit
```

## What lives where

- **Postgres** — `Work`, `Version`, `Download`, `ProcessedScore`
  (`piece_data`, `bar_boxes`, bpm, time signature), `ProcessedPage`
  (MusicXML text, notes JSON, markings JSON).
- **Filesystem (`backend/storage/`)** — the downloaded/enhanced PDFs and the
  rendered page/debug/markings-debug PNGs. The DB stores their paths only.

If audio or other large binaries are added later, the `minio` (S3-compatible)
service in `docker-compose.yml` is the intended home for those bytes, with the
object key stored in Postgres.
