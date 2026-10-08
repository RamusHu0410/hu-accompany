"""Read-only access to the PDMX catalog (services/music_src/pdmx.db).

The catalog was built separately and is never written to from here: it is
opened with SQLite's read-only URI mode, and every clean-up below happens
on the values read out of it.
"""

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

# Composer values in PDMX that mean "nobody filled this in".
_PLACEHOLDER_COMPOSERS = {"", "na", "n/a", "composer", "unknown", "none"}

# Characters that show up when UTF-8 text was decoded as Latin-1 / CP1252
# somewhere upstream, e.g. "FrÃ©dÃ©ric" for "Frédéric".
_MOJIBAKE_HINT = re.compile("[ÃÂâÅå]")


@dataclass(frozen=True)
class CatalogEntry:
    title: str
    composer: str
    mxl: str  # relative to the PDMX root, without the leading "./"
    rating: float


def iter_entries(db_path: Path, min_rating: float, limit: int | None = None):
    """Deduplicated, rated entries with a real composer and an .mxl file,
    best-rated first."""
    query = """
        SELECT title, composer_name, mxl, rating
        FROM pieces
        WHERE is_deduplicated = 1
          AND rating >= ?
          AND mxl NOT IN ('', 'N/A', 'NA')
        ORDER BY rating DESC
    """
    uri = f"file:{db_path}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        yielded = 0
        for title, composer, mxl, rating in conn.execute(query, (min_rating,)):
            composer = clean_text(composer or "")
            if composer.lower() in _PLACEHOLDER_COMPOSERS:
                continue
            yield CatalogEntry(
                title=clean_text(title or "") or "Untitled",
                composer=composer,
                mxl=(mxl or "").removeprefix("./"),
                rating=float(rating or 0),
            )
            yielded += 1
            if limit is not None and yielded >= limit:
                return


def clean_text(value: str) -> str:
    """Repairs double-encoded UTF-8 and collapses whitespace."""
    return " ".join(fix_mojibake(value).split())


def fix_mojibake(value: str) -> str:
    if not _MOJIBAKE_HINT.search(value):
        return value
    for encoding in ("cp1252", "latin-1"):
        try:
            return value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    # Not reversible (e.g. a genuine "Håkan"): keep what the catalog had.
    return value
