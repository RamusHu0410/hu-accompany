import sqlite3
import csv
import sys
import zipfile
import xml.etree.ElementTree as ET

DB_PATH = "pdmx.db"
CSV_PATH = "PDMX.csv"
LIMIT = 5


def init_db():
    _ = csv.field_size_limit(sys.maxsize)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    _ = cur.execute("DROP TABLE IF EXISTS pieces")
    _ = cur.execute("""
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
                    1 if row.get("subset:deduplicated") in ("True", "1", "true") else 0,
                )
            )
            if len(rows) >= 50_000:  # batch insert for speed
                _ = cur.executemany("INSERT INTO pieces VALUES (?,?,?,?,?,?,?,?)", rows)
                rows = []
        if rows:
            _ = cur.executemany("INSERT INTO pieces VALUES (?,?,?,?,?,?,?,?)", rows)

    _ = cur.execute("CREATE INDEX idx_composer ON pieces(composer_name COLLATE NOCASE)")
    _ = cur.execute("CREATE INDEX idx_title ON pieces(title COLLATE NOCASE)")
    _ = cur.execute("CREATE INDEX idx_rating ON pieces(rating DESC)")

    conn.commit()
    conn.close()
    print("Done.")


def fetch_score_pdmx(composer: str, piece_name: str) -> list[sqlite3.Cursor]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    _ = cur.execute(
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


def extract_musicxml(mxl_path: str, out_path: str | None) -> str:
    with zipfile.ZipFile(mxl_path) as z:
        rootfile = None
        try:
            container = z.read("META-INF/container.xml")
            root = ET.fromstring(container)
            elem = root.find(".//{*}rootfile")  # wildcard-namespace match
            if elem is not None:
                rootfile = elem.attrib.get("full-path")
        except (KeyError, ET.ParseError):
            pass

        if not rootfile:
            # fallback: grab the first .xml/.musicxml that isn't container.xml
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
        out_path = mxl_path.rsplit(".", 1)[0] + ".musicxml"
    with open(out_path, "wb") as f:
        _ = f.write(data)
    return out_path
