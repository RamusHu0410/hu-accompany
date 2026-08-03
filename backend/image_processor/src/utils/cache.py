"""Content-hash based caching so re-running the pipeline on an unchanged PDF
skips expensive work (rendering, and later phases) instead of redoing it.
"""

import hashlib
from pathlib import Path


def file_content_hash(path: Path, length: int = 16) -> str:
    """Short, stable hash of a file's bytes - used to key caches per-PDF
    so edits to the source file invalidate the cache automatically."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def render_cache_dir(cache_root: Path, pdf_hash: str, dpi: int) -> Path:
    return cache_root / "renders" / f"{pdf_hash}_dpi{dpi}"


def detection_cache_dir(cache_root: Path, image_hash: str) -> Path:
    return cache_root / "oemer" / image_hash
