"""manage.py import_pdmx -- bring PDMX scores into the Score table.

Reads the catalog and the .mxl files read-only; the only things written are
the extracted .musicxml files under STORAGE_ROOT/musicxml/, the Score rows,
and a skip report next to them. Safe to re-run: rows already imported are
recognised by their catalog path and skipped.

    python manage.py import_pdmx --pdmx-root /path/to/PDMX --limit 200
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from scores import catalog
from scores.models import Score
from scores.musicxml import InvalidMusicXML, inspect, read_musicxml

DEFAULT_CATALOG = settings.BASE_DIR / "services" / "music_src" / "pdmx.db"
OUTPUT_DIR = "musicxml"


class Command(BaseCommand):
    help = "Import rated, deduplicated PDMX scores as MusicXML."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pdmx-root",
            type=Path,
            default=DEFAULT_CATALOG.parent,
            help="Folder containing PDMX's mxl/ directory.",
        )
        parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
        parser.add_argument("--min-rating", type=float, default=4.0)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report without writing files or rows.",
        )

    def handle(self, *args, **opts):
        if not opts["catalog"].is_file():
            raise CommandError(f"catalog not found: {opts['catalog']}")
        if not (opts["pdmx_root"] / "mxl").is_dir():
            raise CommandError(f"no mxl/ folder under {opts['pdmx_root']}")

        out_dir = Path(settings.STORAGE_ROOT) / OUTPUT_DIR
        if not opts["dry_run"]:
            out_dir.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        skipped = []
        entries = catalog.iter_entries(
            opts["catalog"], opts["min_rating"], opts["limit"]
        )
        for entry in entries:
            reason = self._import_one(entry, opts["pdmx_root"], out_dir, opts["dry_run"])
            counts[reason or "imported"] += 1
            if reason:
                skipped.append({"mxl": entry.mxl, "title": entry.title, "reason": reason})

        if not opts["dry_run"]:
            report = out_dir / "import_report.json"
            report.write_text(json.dumps(skipped, indent=2, ensure_ascii=False))
            self.stdout.write(f"skip report: {report}")
        for key, n in sorted(counts.items()):
            self.stdout.write(f"{key}: {n}")

    def _import_one(self, entry, pdmx_root: Path, out_dir: Path, dry_run: bool) -> str | None:
        """Imports one entry; returns why it was skipped, or None."""
        if Score.objects.filter(pdmx_path=entry.mxl).exists():
            return "already imported"

        source = pdmx_root / entry.mxl
        if not source.is_file():
            return "missing file"

        try:
            xml = read_musicxml(source)
            facts = inspect(xml)
        except InvalidMusicXML as e:
            return f"invalid: {e}"

        digest = hashlib.sha256(xml).hexdigest()
        if Score.objects.filter(sha256=digest).exists():
            return "duplicate content"
        if dry_run:
            return None

        relative = Path(OUTPUT_DIR) / f"{Path(entry.mxl).stem}.musicxml"
        (Path(settings.STORAGE_ROOT) / relative).write_bytes(xml)
        Score.objects.create(
            title=entry.title[:500],
            composer=entry.composer[:300],
            rating=entry.rating,
            pdmx_path=entry.mxl,
            musicxml_path=str(relative),
            sha256=digest,
            part_count=facts.part_count,
            measure_count=facts.measure_count,
            time_signature=facts.time_signature,
            tempo_bpm=facts.tempo_bpm,
        )
        return None
