# Storage & Database Guide

## What lives where
- **This folder (`backend/storage/`)** — files only:
  - `scores/` — downloaded PDFs, enhanced PDFs, rendered page/debug PNGs
  - `feedback/` — feedback JSON sessions
- **PostgreSQL** — all structured data:
  - `api_processedscore` — `piece_data`, `bar_boxes`, `bpm`, `time_signature`, PDF paths
  - `api_processedpage` — MusicXML, notes JSON, markings JSON, PNG paths
  - `api_work`, `api_version`, `imslp_downloader_download`
- DB stores only the **paths** to files here, never the file bytes.

## Start the database
1. Open the **Docker Desktop** app (wait for "Docker Desktop is running").
2. From `backend/`:
   ```bash
   docker compose up -d        # start Postgres on localhost:5432
   source .venv/bin/activate
   python manage.py migrate    # create tables
   ```

## Connection details
| Field    | Value                |
|----------|----------------------|
| Host     | `localhost`          |
| Port     | `5432`               |
| Database | `music_catalog`      |
| Username | `app`                |
| Password | `local_dev_password` |

## View the data in pgAdmin
1. Right-click **Servers** → **Register** → **Server…**
2. **General** → Name: `hu-accompany local`
3. **Connection** → enter the details above → check **Save password** → **Save**
4. Expand: `Servers → hu-accompany local → Databases → music_catalog → Schemas → public → Tables`
5. Right-click a table → **View/Edit Data** → **All Rows**

## View the data without pgAdmin
```bash
docker compose exec postgres psql -U app -d music_catalog
```
```sql
\dt                          -- list tables
\d api_processedscore        -- describe a table
SELECT * FROM api_processedscore;
\q                           -- quit
```

## Everyday Docker commands
```bash
docker compose stop     # pause the DB (keeps data)
docker compose up -d    # start it again
docker compose down     # remove container (keeps data volume)
```
- ⚠️ Never run `docker compose down -v` unless you want to **delete all DB data**.

## Notes
- Tables stay empty until the OMR pipeline runs (`POST /api/score/process`) — that writes the rows.
