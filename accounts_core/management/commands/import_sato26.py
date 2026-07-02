"""Import SATO26 staging data into Sama Accounting."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from migration.sato26.extract_staging import main as extract_main
from migration.sato26.load_staging import Sato26Importer


class Command(BaseCommand):
    help = "Extract SATO26 legacy data to staging JSON and/or import into Sama Accounting."

    def add_arguments(self, parser):
        parser.add_argument(
            "--extract-only",
            action="store_true",
            help="Only run SQL/CSV → staging extraction.",
        )
        parser.add_argument(
            "--import-only",
            action="store_true",
            help="Only import existing staging (skip extraction).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count records without writing to the database.",
        )
        parser.add_argument(
            "--staging-dir",
            type=str,
            default="",
            help="Staging folder (default: exports/sato26/staging).",
        )
        parser.add_argument(
            "--steps",
            type=str,
            default="",
            help=(
                "Comma-separated import steps: service_types,clients,suppliers,setup,"
                "invoices,supplier_bills,payments"
            ),
        )

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        staging_dir = Path(options["staging_dir"]) if options["staging_dir"] else base / "exports" / "sato26" / "staging"

        if not options["import_only"]:
            self.stdout.write("Extracting SATO26 → staging JSON...")
            extract_main()

        if options["extract_only"]:
            self.stdout.write(self.style.SUCCESS(f"Staging ready at {staging_dir}"))
            manifest = staging_dir / "manifest.json"
            if manifest.exists():
                self.stdout.write(manifest.read_text(encoding="utf-8"))
            return

        if not staging_dir.exists():
            raise CommandError(f"Staging not found: {staging_dir}. Run without --import-only first.")

        steps = [s.strip() for s in options["steps"].split(",") if s.strip()] or None
        importer = Sato26Importer(staging_dir, dry_run=options["dry_run"])
        stats = importer.run(steps=steps)

        self.stdout.write(self.style.SUCCESS(json.dumps(stats, indent=2)))
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no database changes made."))
        else:
            self.stdout.write(self.style.SUCCESS("SATO26 import completed."))
