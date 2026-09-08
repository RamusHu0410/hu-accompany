"""On-disk persistence for generated feedback.

One directory per practice session, named `<date>-<piece>`, with one file per
phrase in phase 1 and one file per phase-2 judge:

    storage/feedback/2026-09-07-Prelude_in_C/
      Phase1/
        Phrase1.json      # judge_phrase() body + piece/recorded_at header
        Phrase2.json
      Phase2/
        Summary.json      # summarizer.summarize()
        Era.json          # judges/phase2/era.py

Mirrors pdf_processor, which writes its piece_data JSON into storage rather
than a DB table -- there is no Django model for feedback. Unlike
imslp_downloader/storage.py, this module does *not* read
django.conf.settings: feedback_generator stays framework-free, so the caller
passes the storage root in (api/views.py passes settings.STORAGE_ROOT).

Phrase files are addressed by phrase number, so re-recording a phrase
overwrites that one file and leaves the rest of the session untouched --
phase 2 then summarizes the latest take of every phrase.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .errors import InvalidSessionId, StorageFailed

FEEDBACK_DIR_NAME = "feedback"
PHASE1_DIR_NAME = "Phase1"
PHASE2_DIR_NAME = "Phase2"
DATE_FORMAT = "%Y-%m-%d"
UNTITLED_PIECE = "Untitled"

# Session ids become path segments, so they're restricted to characters that
# can't escape the feedback directory.
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,128}\Z")
_SLUG_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")
_PHRASE_FILE_RE = re.compile(r"\APhrase(\d+)\.json\Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text) -> str:
    """A filesystem-safe fragment of a piece title: "Prelude in C (No. 1)"
    -> "Prelude_in_C_No_1"."""
    slug = _SLUG_STRIP_RE.sub("_", str(text or "")).strip("_")
    return slug or UNTITLED_PIECE


def session_id_for(piece: Optional[dict] = None, created_at: Optional[datetime] = None) -> str:
    """The `<date>-<piece>` directory name for a session. Deterministic, so
    every phrase of the same piece on the same day lands in one directory
    without the client having to track an id."""
    title = (piece or {}).get("title") if isinstance(piece, dict) else None
    return f"{(created_at or _now()).strftime(DATE_FORMAT)}-{slugify(title)}"


def validate_session_id(session_id) -> str:
    """Return `session_id` unchanged if it's a plain identifier, else raise.
    Rejects rather than sanitizes so a caller never silently writes to a
    different session's directory than the one it asked for."""
    if not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id) or ".." in session_id:
        raise InvalidSessionId(
            f"session_id must be 1-128 characters of [A-Za-z0-9_.-]; got {session_id!r}"
        )
    return session_id


# --- Paths -------------------------------------------------------------------

def feedback_root(storage_root) -> Path:
    return Path(storage_root) / FEEDBACK_DIR_NAME


def session_dir(storage_root, session_id: str) -> Path:
    validate_session_id(session_id)
    return feedback_root(storage_root) / session_id


def phrase_path(storage_root, session_id: str, phrase: int) -> Path:
    return session_dir(storage_root, session_id) / PHASE1_DIR_NAME / f"Phrase{int(phrase)}.json"


def phase2_path(storage_root, session_id: str, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(name)):
        raise InvalidSessionId(f"phase-2 file name must be [A-Za-z0-9_-]; got {name!r}")
    return session_dir(storage_root, session_id) / PHASE2_DIR_NAME / f"{name}.json"


def list_sessions(storage_root) -> List[str]:
    """Every session directory name, oldest date first."""
    root = feedback_root(storage_root)
    return sorted(child.name for child in root.glob("*") if child.is_dir())


# --- Read / write ------------------------------------------------------------

def read_json(path) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except OSError as exc:
        raise StorageFailed(f"Could not read feedback file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StorageFailed(f"Feedback file {path} is not valid JSON: {exc}") from exc


def write_json(path: Path, payload: dict) -> None:
    """Write via a temp file + os.replace so an interrupted write can't leave
    a half-written file behind."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise StorageFailed(f"Could not write feedback file {path}: {exc}") from exc


def save_phrase(
    storage_root,
    result: dict,
    session_id: Optional[str] = None,
    piece: Optional[dict] = None,
) -> tuple:
    """Write one judge_phrase() result to Phase1/Phrase<n>.json.

    `session_id` defaults to `<today>-<piece title>`; `piece` is
    caller-supplied metadata (title/composer/composed_date/...) stored as-is
    in the file header, which is where phase 2 reads it back from. Returns
    (session_id, path_of_written_file). Raises StorageFailed on I/O trouble
    and InvalidSessionId on a malformed id.
    """
    if session_id is None:
        session_id = session_id_for(piece)
    validate_session_id(session_id)

    entry = {"piece": piece or None, "recorded_at": _now().isoformat(), **result}
    path = phrase_path(storage_root, session_id, result["phrase"])
    write_json(path, entry)
    return session_id, path


def load_phrases(storage_root, session_id: str) -> List[dict]:
    """Every stored phase-1 phrase of a session, in phrase order -- what
    phase 2 runs on."""
    directory = session_dir(storage_root, session_id) / PHASE1_DIR_NAME
    numbered = []
    for path in directory.glob("Phrase*.json"):
        match = _PHRASE_FILE_RE.match(path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    return [read_json(path) for _, path in sorted(numbered)]


def load_piece(phrases: List[dict]) -> Optional[dict]:
    """The piece metadata recorded with a session's phrases -- the latest
    non-empty one wins, since a phrase can be re-recorded with better
    metadata than the first take had."""
    piece = None
    for entry in phrases:
        if entry.get("piece"):
            piece = entry["piece"]
    return piece


def save_phase2(storage_root, session_id: str, files: Dict[str, dict]) -> Dict[str, Path]:
    """Write judge_piece()'s output, one file per key, into Phase2/.
    Overwrites: phase 2 is a snapshot of every phrase judged so far, so it
    is re-runnable after any new take."""
    validate_session_id(session_id)
    written = {}
    for name, payload in files.items():
        path = phase2_path(storage_root, session_id, name)
        write_json(path, payload)
        written[name] = path
    return written
