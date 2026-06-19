"""Import client master records from legacy ERP PDF exports."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts_core.legacy_import.client_pdf import (
    build_import_notes,
    discover_client_rows,
    legacy_client_code,
)
from accounts_core.models import Client


class Command(BaseCommand):
    help = "Import clients from legacy PDF exports in old data/Clients."

    def add_arguments(self, parser):
        default_dir = Path(settings.BASE_DIR).parent / "old data" / "Clients"
        parser.add_argument(
            "--dir",
            dest="clients_dir",
            default=str(default_dir),
            help=f"Folder containing legacy client PDFs (default: {default_dir})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without writing to the database.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update notes/name on clients already imported (matched by legacy account in notes or client code).",
        )

    def handle(self, *args, **options):
        clients_dir = Path(options["clients_dir"]).expanduser().resolve()
        dry_run = options["dry_run"]
        update_existing = options["update_existing"]

        try:
            rows = discover_client_rows(clients_dir)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        if not rows:
            raise CommandError(f"No clients parsed from {clients_dir}")

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for row in rows:
                code = legacy_client_code(row.legacy_account)
                notes = build_import_notes(row)
                contact = row.name_en if row.client_type == "CORPORATE" else ""
                phone = row.phone or "00000000"

                existing = Client.objects.filter(client_code=code).first()
                if not existing:
                    existing = Client.objects.filter(notes__contains=row.legacy_account).first()

                if existing and not update_existing:
                    skipped += 1
                    self.stdout.write(f"  skip  {code} {row.name_en} (already exists)")
                    continue

                if dry_run:
                    action = "update" if existing else "create"
                    self.stdout.write(
                        f"  {action} {code} | {row.legacy_account} | {row.name_en} | "
                        f"balance {row.closing_balance} {row.currency}"
                    )
                    if existing:
                        updated += 1
                    else:
                        created += 1
                    continue

                if existing:
                    existing.name_en = row.name_en
                    existing.type = row.client_type
                    existing.notes = notes
                    if row.address:
                        existing.address = row.address
                    if row.phone:
                        existing.phone = row.phone
                    if contact:
                        existing.contact_person = contact
                    existing.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(f"  updated {code} {row.name_en}"))
                else:
                    Client.objects.create(
                        client_code=code,
                        type=row.client_type,
                        name_en=row.name_en,
                        phone=phone,
                        contact_person=contact,
                        address=row.address,
                        notes=notes,
                    )
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"  created {code} {row.name_en}"))

            if dry_run:
                transaction.set_rollback(True)

        label = "Dry run — " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}Done: {created} created, {updated} updated, {skipped} skipped "
                f"({len(rows)} rows in PDF export)."
            )
        )
