"""Where the hum feature keeps its files.

Deliberately outside STORAGE_ROOT: server/urls.py serves everything under storage/ to anyone who
asks, and users' hums must never be reachable by URL.
"""

from pathlib import Path

from django.conf import settings


def data_dir() -> Path:
    return Path(getattr(settings, "HUM_DATA_DIR", settings.BASE_DIR / "hum_data"))


def upload_dir() -> Path:
    """The WAVs users hummed. POST /api/hum/upload saves them here under a unique name."""
    folder = data_dir() / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def runs_dir() -> Path:
    """One folder per song the epic engine makes: every step's files and a log."""
    folder = data_dir() / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def saved_hum(name: str) -> Path | None:
    """The upload called `name`, or None if there isn't one. The name is cleaned first, so it
    can't point outside the uploads folder."""
    from hum.engine.audio.intake.checks import secure_filename

    path = upload_dir() / secure_filename(name)
    return path if path.is_file() else None
