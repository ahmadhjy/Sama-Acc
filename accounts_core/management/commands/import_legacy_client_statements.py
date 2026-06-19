"""Import client statement history from legacy SOA PDF exports."""

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts_core.legacy_import.client_soa import discover_client_soa_files, load_soa_pdf
from accounts_core.legacy_import.defaults import find_client_by_legacy_account, get_legacy_import_context
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment


class Command(BaseCommand):
    help = (
        "Import client statement transactions from legacy SOA PDFs. "
        "Creates posted legacy invoices (debits) and payments (credits). "
        "Run import_legacy_clients first."
    )

    def add_arguments(self, parser):
        default_dir = Path(settings.BASE_DIR).parent / "old data" / "Clients"
        parser.add_argument("--dir", dest="clients_dir", default=str(default_dir))
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--account",
            dest="legacy_account",
            help="Import only one legacy account (e.g. 4110000505).",
        )
        parser.add_argument(
            "--skip-before-request",
            action="store_true",
            help="Skip the large 'Clients Before Request 2025' SOA file.",
        )

    def handle(self, *args, **options):
        clients_dir = Path(options["clients_dir"]).expanduser().resolve()
        dry_run = options["dry_run"]
        only_account = options.get("legacy_account")
        skip_before = options["skip_before_request"]

        try:
            paths = discover_client_soa_files(clients_dir)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        if skip_before:
            paths = [p for p in paths if "Before Request" not in p.name]

        if only_account:
            filtered = []
            for p in paths:
                try:
                    acct, _, _ = load_soa_pdf(p)
                    if acct == only_account:
                        filtered.append(p)
                except ValueError:
                    continue
            paths = filtered

        if not paths:
            raise CommandError("No client SOA PDF files found to import.")

        ctx = None if dry_run else get_legacy_import_context()
        inv_created = pay_created = skipped = 0

        with transaction.atomic():
            for path in paths:
                try:
                    legacy_account, client_name, txs = load_soa_pdf(path)
                except ValueError as exc:
                    self.stdout.write(self.style.WARNING(f"  skip {path.name}: {exc}"))
                    continue

                if only_account and legacy_account != only_account:
                    continue

                client = None if dry_run else find_client_by_legacy_account(legacy_account)
                if not dry_run and not client:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  skip {path.name}: client for {legacy_account} not found — run import_legacy_clients first"
                        )
                    )
                    continue

                self.stdout.write(f"\n{path.name} — {client_name} ({legacy_account}) — {len(txs)} monetary rows")

                for idx, tx in enumerate(txs, start=1):
                    suffix = f"{legacy_account[-4:]}-{tx.jv_no}-{tx.trans_date.strftime('%Y%m%d')}-{idx}"

                    if tx.is_payment:
                        amount = tx.payment_amount
                        if amount <= 0:
                            skipped += 1
                            continue
                        receipt_no = f"LEG-RCPT-{suffix}"
                        if not dry_run and Payment.objects.filter(receipt_no=receipt_no).exists():
                            skipped += 1
                            continue
                        if dry_run:
                            self.stdout.write(
                                f"    payment {receipt_no} {tx.trans_date} {amount} USD — {tx.description[:60]}"
                            )
                            pay_created += 1
                            continue
                        Payment.objects.create(
                            receipt_no=receipt_no,
                            direction=Payment.Direction.IN,
                            party_type=Payment.PartyType.CLIENT,
                            client=client,
                            money_account=ctx["money_account"],
                            payment_method="LEGACY",
                            date=tx.trans_date,
                            currency="USD",
                            amount=amount,
                            reference=f"Legacy JV#{tx.jv_no}",
                            note=tx.description[:2000],
                            status=Payment.Status.POSTED,
                            posted_at=timezone.now(),
                        )
                        pay_created += 1
                    else:
                        amount = tx.invoice_amount
                        if amount <= 0:
                            skipped += 1
                            continue
                        invoice_no = f"LEG-INV-{suffix}"
                        if not dry_run and SalesInvoice.objects.filter(invoice_no=invoice_no).exists():
                            skipped += 1
                            continue
                        if dry_run:
                            self.stdout.write(
                                f"    invoice {invoice_no} {tx.trans_date} {amount} USD — {tx.description[:60]}"
                            )
                            inv_created += 1
                            continue
                        inv = SalesInvoice.objects.create(
                            invoice_no=invoice_no,
                            client=client,
                            sales_employee=ctx["employee"],
                            issue_date=tx.trans_date,
                            due_date=tx.trans_date,
                            currency="USD",
                            exchange_rate_to_usd=None,
                            status=SalesInvoice.Status.POSTED,
                            posted_at=timezone.now(),
                            subtotal=amount,
                            grand_total=amount,
                            subtotal_usd=amount,
                            grand_total_usd=amount,
                            package_type=SalesInvoice.PackageType.TICKET,
                        )
                        SalesInvoiceLine.objects.create(
                            invoice=inv,
                            service_type=ctx["service_type"],
                            supplier=ctx["supplier"],
                            destination=ctx["destination"],
                            line_employee=ctx["employee"],
                            service_date=tx.trans_date,
                            qty=Decimal("1"),
                            sell_price=amount,
                            sell_price_usd=amount,
                            cost_price=Decimal("0"),
                            cost_price_usd=Decimal("0"),
                            line_data={"legacy_description": tx.description[:500]},
                            notes=f"Legacy JV#{tx.jv_no} — imported from {path.name}",
                        )
                        inv_created += 1

            if dry_run:
                transaction.set_rollback(True)

        label = "Dry run — " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{label}Done: {inv_created} legacy invoice(s), {pay_created} legacy payment(s), "
                f"{skipped} skipped."
            )
        )
        if not dry_run:
            self.stdout.write(
                "Open Client Statement in the app to verify balances match the legacy SOA PDFs."
            )
