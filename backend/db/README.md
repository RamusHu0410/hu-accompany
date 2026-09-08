Database development

This directory will contain the Python database layer for the music catalogue.
PostgreSQL stores composers, pieces, MusicXML score sources, users, and other
structured metadata. It does **not** store large media such as audio files;
those can be added through S3-compatible storage later.

## Prerequisites

- Docker Desktop (or Docker Engine with Compose)
- Python 3.11 or newer

## Start PostgreSQL locally

From the repository root, start the PostgreSQL service:

```bash
docker compose up -d
```

Check that it is running:

```bash
docker compose ps
```

Stop the local database when it is no longer needed:

```bash
docker compose down
```

`docker compose down` stops the container but retains its named database
volume. Do not run `docker compose down -v` unless you intentionally want to
delete all local database data.

## Python setup

Create and activate a virtual environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repository root. Never commit it.

```env
DATABASE_URL=postgresql+psycopg://app:local_dev_password@localhost:5432/music_catalog
```

The username, password, database name, and port must match the `postgres`
service configuration in `docker-compose.yml`.

## Create the tables

For the initial local schema, run:

```bash
python -m app.init_db
```

This creates the tables defined in `app/models.py`:

- `composers`
- `pieces`
- `score_sources`

Once the project starts evolving its schema, use Alembic migrations rather than
changing a shared database with `create_all()`.

## Access the database directly

Open the PostgreSQL command-line client inside the running container:

```bash
docker compose exec postgres psql -U app -d music_catalog
```

Useful `psql` commands:

```sql
\dt                         -- list tables
\d composers                -- describe a table
SELECT * FROM composers;    -- inspect records
\q                          -- quit
```

Use the host address `localhost` when connecting from Python or a desktop SQL
client. Use the Docker service name `postgres` only when another Docker
container needs to connect to the database.

## Reset local data

This permanently removes the local database volume and all of its contents:

```bash
docker compose down -v
docker compose up -d
python -m app.init_db
```

Only run this against local development data.

## MusicXML now; object storage later

MusicXML is stored as text in Postgres (`score_sources.content`) and retrieved
by the API for the client to render with Verovio. When audio, PDFs, scans, or
other large binary files are added, introduce MinIO locally and a hosted
S3-compatible service in production. Postgres will store each file's metadata
and object key; the object store will hold the file bytes.

