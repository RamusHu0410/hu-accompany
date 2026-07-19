"""Database and API schemas for the IMSLP downloader.

`Download` is the persisted record (Phase 1/6 of the design doc); the two
dataclasses describe the request/response shape of POST /api/imslp/download
(Phase 2) independently of Django, so api.py stays a thin translation layer.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import models

from api.models import Version


class DownloadStatus(models.TextChoices):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Download(models.Model):
    # `score` is a best-effort link to the metadata service's Version row;
    # kept nullable + paired with score_id_raw so a download record (and its
    # cache-hit lookup) survives even if that row is later evicted/missing.
    score = models.ForeignKey(
        Version, related_name="downloads", null=True, blank=True, on_delete=models.SET_NULL
    )
    score_id_raw = models.CharField(max_length=100, db_index=True)
    imslp_url = models.URLField(max_length=1000)

    status = models.CharField(
        max_length=20, choices=DownloadStatus.choices, default=DownloadStatus.PENDING
    )
    error_message = models.TextField(blank=True, null=True)

    file_path = models.CharField(max_length=1000, blank=True, null=True)
    file_name = models.CharField(max_length=500, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Download(score_id={self.score_id_raw}, status={self.status})"


@dataclass
class DownloadRequest:
    score_id: str
    imslp_url: str


@dataclass
class DownloadResponse:
    status: str
    score_id: str
    file_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        body = {"status": self.status, "score_id": self.score_id}
        if self.file_path is not None:
            body["file_path"] = self.file_path
        if self.error is not None:
            body["error"] = self.error
        return body
