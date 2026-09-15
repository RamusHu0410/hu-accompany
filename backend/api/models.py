from django.db import models


class Work(models.Model):
    title = models.CharField(max_length=500)
    composer = models.CharField(max_length=500, blank=True)
    imslp_url = models.URLField(max_length=1000, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.composer})"


class Version(models.Model):
    work = models.ForeignKey(Work, related_name="versions", on_delete=models.CASCADE)
    name = models.CharField(max_length=500)
    instrumentation = models.CharField(max_length=500, blank=True)
    type = models.CharField(max_length=50)
    movement = models.CharField(max_length=500, blank=True, null=True)
    arranger = models.CharField(max_length=500, blank=True, null=True)
    editor = models.CharField(max_length=500, blank=True, null=True)
    imslp_url = models.URLField(max_length=1000)
    file_name = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.name} [{self.work_id}]"


class ProcessedScore(models.Model):
    """The result of running the OMR pipeline (pdf_processor.process) on one
    score PDF.

    All of the pipeline's *structured* output lives here in Postgres --
    piece_data, bar_boxes, tempo/time-signature. The large binary artifacts
    (the source/enhanced PDFs and the rendered page/debug PNGs) stay on disk
    under settings.STORAGE_ROOT; only their storage-relative paths are kept
    in the DB (see ProcessedPage). This is the "everything except the files
    themselves goes in Postgres" split.
    """

    # The source PDF this was produced from, as a "storage/scores/..." db
    # path (the same string imslp_downloader.storage.to_db_path yields and
    # /api/imslp/download returns). Unique so re-processing the same PDF
    # replaces its row rather than piling up duplicates.
    source_pdf_path = models.CharField(max_length=1000, unique=True)

    # The cleaned-up PDF that Part 1 actually splits/OMRs, kept on disk as a
    # "storage/..." db path.
    enhanced_pdf_path = models.CharField(max_length=1000, blank=True)

    bpm = models.FloatField(null=True, blank=True)
    time_signature = models.CharField(max_length=20, blank=True)

    # Whole-piece structured output. piece_data matches the downstream Rust
    # consumer's PieceData struct; bar_boxes is where each bar sits on the
    # page in pixels. Stored as JSONB.
    piece_data = models.JSONField(default=dict)
    bar_boxes = models.JSONField(default=list)

    # Timing breakdown of the pipeline run (seconds per phase).
    timing = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ProcessedScore({self.source_pdf_path})"


class ProcessedPage(models.Model):
    """Per-page output of the OMR pipeline for one ProcessedScore.

    The structured data (MusicXML text, the page's notes and markings JSON)
    is stored inline in Postgres. The rendered images -- the page PNG, the
    note/clef/barline debug PNG, and the markings debug PNG -- stay on disk;
    only their "storage/..." db paths are recorded here.
    """

    score = models.ForeignKey(
        ProcessedScore, related_name="pages", on_delete=models.CASCADE
    )
    # 1-based page number within the piece.
    page_number = models.PositiveIntegerField()

    # On-disk image artifacts, kept as "storage/..." db paths.
    page_png_path = models.CharField(max_length=1000, blank=True)
    debug_png_path = models.CharField(max_length=1000, blank=True)
    markings_debug_png_path = models.CharField(max_length=1000, blank=True)

    # Structured output stored directly in Postgres.
    musicxml = models.TextField(blank=True)
    notes_json = models.JSONField(default=dict)
    markings_json = models.JSONField(default=list)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["score", "page_number"], name="uniq_score_page"
            )
        ]

    def __str__(self):
        return f"ProcessedPage({self.score_id}, page {self.page_number})"
