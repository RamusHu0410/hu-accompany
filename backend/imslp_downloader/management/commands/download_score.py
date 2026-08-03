"""Manual/E2E test tool: run the real download flow (real headless browser,
real network, real disk write) against a single IMSLP URL, without needing
the API server running or a matching Version row in the DB."""

import uuid

from django.core.management.base import BaseCommand, CommandError

from ... import downloader
from ...exceptions import IMSLPDownloaderError


class Command(BaseCommand):
    help = (
        "Download a score directly from an IMSLP file URL and save it under "
        "storage/. Drives a real headless browser through IMSLP's disclaimer/"
        "subscribe flow, so it can take up to a few minutes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "imslp_url",
            help="Direct IMSLP file URL, e.g. "
            "https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/IMSLP00000-...",
        )
        parser.add_argument(
            "--score-id",
            default=None,
            help="score_id to tag the Download record with, and to look up a "
            "matching Version (its imslp_url wins over the one given here if "
            "found). Defaults to a random id, i.e. no Version lookup.",
        )

    def handle(self, *args, **options):
        imslp_url = options["imslp_url"]
        score_id = options["score_id"] or f"manual-{uuid.uuid4().hex[:8]}"

        existing = downloader.find_existing(score_id)
        if existing:
            self.stdout.write(self.style.WARNING(f"Already downloaded: {existing.file_path}"))
            return

        self.stdout.write(f"Downloading {imslp_url} ...")
        try:
            record = downloader.download(score_id, imslp_url)
        except IMSLPDownloaderError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Saved to {record.file_path} ({record.file_size} bytes)")
        )
