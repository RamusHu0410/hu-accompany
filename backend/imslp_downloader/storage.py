"""File management for downloaded IMSLP PDFs.

Paths handed around this module come in two flavors:
- a "storage-relative" Path, rooted at settings.STORAGE_ROOT (e.g.
  scores/Beethoven/Piano_Sonata_No.14/piano_solo.pdf) -- what disk
  operations use.
- a "db path" string, rooted at BASE_DIR (e.g.
  storage/scores/Beethoven/Piano_Sonata_No.14/piano_solo.pdf) -- what gets
  stored in Download.file_path and returned to the frontend, matching the
  API contract's "storage/scores/..." example.
"""

import re
import shutil
from pathlib import Path

from django.conf import settings

from .exceptions import FileSaveFailed

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PDF_MAGIC = b"%PDF-"


def _slugify(text: str, default: str) -> str:
    text = (text or "").strip().replace(" ", "_")
    text = _UNSAFE_RE.sub("_", text)
    text = text.strip("_.")
    return text or default


def _composer_last_name(composer: str) -> str:
    """"Beethoven, Ludwig van" -> "Beethoven"."""
    first_token = (composer or "").split(",")[0]
    return _slugify(first_token, "Unknown")


def build_relative_path(work_title: str, composer: str, choice_name: str, file_name: str) -> Path:
    ext = Path(file_name or "").suffix or ".pdf"
    return (
        Path("scores")
        / _composer_last_name(composer)
        / _slugify(work_title, "Untitled_Work")
        / f"{_slugify(choice_name, 'score')}{ext}"
    )


def absolute_path(relative_path: Path) -> Path:
    return Path(settings.STORAGE_ROOT) / relative_path


def to_db_path(relative_path: Path) -> str:
    return str(Path("storage") / relative_path)


def db_path_to_absolute(db_path: str) -> Path:
    return Path(settings.BASE_DIR) / db_path


def exists(db_path: str) -> bool:
    return bool(db_path) and db_path_to_absolute(db_path).is_file()


def save(tmp_path, relative_path: Path) -> int:
    """Copy a downloaded file (e.g. a Playwright Download's temp path) into
    permanent storage. Returns the saved file's size in bytes."""
    dest = absolute_path(relative_path)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path, dest)
        return dest.stat().st_size
    except OSError as exc:
        raise FileSaveFailed(f"Could not save PDF to {dest}: {exc}") from exc


def validate_pdf(relative_path: Path) -> None:
    """Raise FileSaveFailed if the saved file isn't a usable PDF."""
    dest = absolute_path(relative_path)
    try:
        size = dest.stat().st_size
        with open(dest, "rb") as f:
            header = f.read(len(_PDF_MAGIC))
    except OSError as exc:
        raise FileSaveFailed(f"Could not validate {dest}: {exc}") from exc

    if size == 0:
        raise FileSaveFailed(f"Downloaded file {dest} is empty")
    if header != _PDF_MAGIC:
        raise FileSaveFailed(f"Downloaded file {dest} is not a valid PDF (bad header)")
