from django.core.management.base import BaseCommand

from sales.models import SalesInvoice


class Command(BaseCommand):
    help = "Activate draft invoices (assign INV numbers, sync supplier bills). Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List draft invoices without changing them.",
        )

    def handle(self, *args, **options):
        drafts = SalesInvoice.objects.filter(status=SalesInvoice.Status.DRAFT).order_by("created_at")
        total = drafts.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No draft invoices found."))
            return

        if options["dry_run"]:
            self.stdout.write(f"Would process {total} draft invoice(s):")
            for inv in drafts:
                self.stdout.write(f"  {inv.invoice_no} — client={inv.client_id or '—'}")
            return

        ok = 0
        skipped = 0
        for inv in drafts:
            try:
                inv.publish_changes()
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"Activated {inv.invoice_no}"))
            except ValueError as exc:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"Skipped {inv.invoice_no}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. Activated {ok}, skipped {skipped} (of {total} drafts).")
        )
