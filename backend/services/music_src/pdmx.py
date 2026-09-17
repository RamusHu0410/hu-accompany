import csv
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path

from db.crud import get_or_create_score
from db.db import SessionLocal

# --- CONFIG ---
PDMX_ROOT = Path(__file__).parent  # folder containing pdmx.py, PDMX.csv, mxl/
CSV_PATH = PDMX_ROOT / "PDMX.csv"
DB_PATH = PDMX_ROOT / "pdmx.db"
LIMIT = 5


def resolve_pdmx_path(relative_path: str) -> Path:
    # relative_path looks like "./mxl/10/44/xyz.mxl"
    return PDMX_ROOT / relative_path.lstrip("./")


def init_db():
    csv.field_size_limit(sys.maxsize)

    # closing() closes the connection; the connection context commits on
    # success and rolls back on failure.
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            cur = conn.cursor()

            # Start the transaction before the DDL so a failed rebuild also
            # rolls back the DROP TABLE and preserves the previous catalog.
            cur.execute("BEGIN")
            cur.execute("DROP TABLE IF EXISTS pieces")
            cur.execute("""
                CREATE TABLE pieces (
                    title TEXT,
                    song_name TEXT,
                    artist_name TEXT,
                    composer_name TEXT,
                    mxl TEXT,
                    path TEXT,
                    rating REAL,
                    is_deduplicated INTEGER
                )
            """)

            with open(CSV_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for row in reader:
                    rows.append(
                        (
                            row.get("title"),
                            row.get("song_name"),
                            row.get("artist_name"),
                            row.get("composer_name"),
                            row.get("mxl"),
                            row.get("path"),
                            float(row["rating"])
                            if row.get("rating") not in (None, "", "N/A")
                            else 0.0,
                            1
                            if row.get("subset:deduplicated")
                            in ("True", "1", "true")
                            else 0,
                        )
                    )
                    if len(rows) >= 50_000:
                        cur.executemany(
                            "INSERT INTO pieces VALUES (?,?,?,?,?,?,?,?)", rows
                        )
                        rows = []
                if rows:
                    cur.executemany(
                        "INSERT INTO pieces VALUES (?,?,?,?,?,?,?,?)", rows
                    )

            cur.execute(
                "CREATE INDEX idx_composer ON pieces(composer_name COLLATE NOCASE)"
            )
            cur.execute("CREATE INDEX idx_title ON pieces(title COLLATE NOCASE)")
            cur.execute("CREATE INDEX idx_rating ON pieces(rating DESC)")

    print("Database built.")


def fetch_score_pdmx(composer: str, piece_name: str) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT title, composer_name, artist_name, mxl, rating
            FROM pieces
            WHERE composer_name LIKE ? COLLATE NOCASE
              AND title LIKE ? COLLATE NOCASE
            ORDER BY is_deduplicated DESC, rating DESC
            LIMIT ?
            """,
            (f"%{composer}%", f"%{piece_name}%", LIMIT),
        )
        return cur.fetchall()


def extract_musicxml(mxl_path: Path, out_path: Path | None = None) -> Path:
    with zipfile.ZipFile(mxl_path) as z:
        rootfile = None
        try:
            container = z.read("META-INF/container.xml")
            root = ET.fromstring(container)
            elem = root.find(".//{*}rootfile")
            if elem is not None:
                rootfile = elem.attrib.get("full-path")
        except (KeyError, ET.ParseError):
            pass

        if not rootfile:
            candidates = [
                n
                for n in z.namelist()
                if n.lower().endswith((".xml", ".musicxml"))
                and "container.xml" not in n
            ]
            if not candidates:
                raise FileNotFoundError(f"No MusicXML found inside {mxl_path}")
            rootfile = candidates[0]

        data = z.read(rootfile)

    if out_path is None:
        out_path = mxl_path.with_suffix(".musicxml")
    out_path.write_bytes(data)
    return out_path


def store_pdmx_piece(composer_name: str, piece_name: str):
    results = fetch_score_pdmx(composer_name, piece_name)
    if not results:
        print("No match found in PDMX.")
        return None
    best = results[0]

    if best["mxl"] in (None, "N/A", ""):
        print("No valid MusicXML for this entry.")
        return None

    mxl_abs_path = resolve_pdmx_path(best["mxl"])
    xml_path = extract_musicxml(mxl_abs_path)
    xml_content = xml_path.read_text(encoding="utf-8")

    with SessionLocal() as db:
        try:
            # The CRUD helper commits when it inserts a new score.
            score, created = get_or_create_score(
                db, best["composer_name"], best["title"], xml_content
            )

            if created:
                print(f"Inserted new score (score_id={score.id})")
            else:
                print(f"Already in DB (score_id={score.id}) — skipped insert")

            return score
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    store_pdmx_piece("Chopin", "Nocturne")
