from django.db import models


class Score(models.Model):
    """One playable piece of sheet music, stored as uncompressed MusicXML.

    Rows are created by `manage.py import_pdmx`, which reads the PDMX
    catalog (services/music_src/pdmx.db) read-only. The XML itself lives on
    disk under STORAGE_ROOT; the row keeps its storage-relative path, the
    same "DB stores paths, not bytes" split the rest of the backend uses.
    """

    title = models.CharField(max_length=500)
    composer = models.CharField(max_length=300, db_index=True)
    rating = models.FloatField(default=0)

    # The catalog's own `mxl` column (e.g. "mxl/2/21/Qm....mxl"), so a
    # re-import recognises a row it already brought in.
    pdmx_path = models.CharField(max_length=500, unique=True)

    # Relative to STORAGE_ROOT, e.g. "musicxml/Qm....musicxml".
    musicxml_path = models.CharField(max_length=500)
    # PDMX carries byte-identical uploads under different names; the hash
    # keeps them from becoming separate search results.
    sha256 = models.CharField(max_length=64, unique=True)

    # Read from the XML at import time so the app knows tempo and metre
    # without parsing the score itself.
    part_count = models.PositiveIntegerField()
    measure_count = models.PositiveIntegerField()
    time_signature = models.CharField(max_length=20, blank=True)
    tempo_bpm = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rating", "title"]

    def __str__(self):
        return f"{self.title} ({self.composer})"

    def as_summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "composer": self.composer,
            "rating": self.rating,
            "part_count": self.part_count,
            "measure_count": self.measure_count,
            "time_signature": self.time_signature,
            "tempo_bpm": self.tempo_bpm,
        }
