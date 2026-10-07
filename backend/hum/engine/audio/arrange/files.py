"""Writing step outputs safely: to a temporary file, validated, then moved into place.

A reader never sees half a file, a file that failed validation never appears under its real name,
and an existing file is never replaced (every step writes NEW files).
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Callable


def _temporary_path(final: Path) -> Path:
    # Same folder (so the final move is a rename) and same extension (libraries pick the format
    # from it), hidden so nobody mistakes it for an output.
    return final.with_name(f".{final.stem}.tmp-{uuid.uuid4().hex[:8]}{final.suffix}")


def write_atomically(
    final_path: str | os.PathLike,
    write: Callable[[Path], None],
    validate: Callable[[Path], object] | None = None,
) -> Path:
    """`write(tmp)` produces the file, `validate(tmp)` raises if it's bad, then it takes its name.

    Raises FileExistsError if `final_path` already exists, before writing anything.
    """
    final = Path(final_path)
    if final.exists():
        raise FileExistsError(f"Refusing to overwrite {final}: every step writes new files.")
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = _temporary_path(final)
    try:
        write(tmp)
        if validate is not None:
            validate(tmp)
        # link() fails if the name was taken meanwhile, so even a race can't overwrite a file.
        os.link(tmp, final)
    finally:
        tmp.unlink(missing_ok=True)
    return final


def copy_atomically(source: str | os.PathLike, final_path: str | os.PathLike, validate=None) -> Path:
    """A new copy of `source` at `final_path`, never replacing anything."""
    return write_atomically(final_path, lambda tmp: shutil.copyfile(source, tmp), validate)


def replace_atomically(final_path: str | os.PathLike, write: Callable[[Path], None]) -> Path:
    """For files that are meant to be rewritten, like a run's log: never half-written."""
    final = Path(final_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = _temporary_path(final)
    try:
        write(tmp)
        os.replace(tmp, final)
    finally:
        tmp.unlink(missing_ok=True)
    return final
