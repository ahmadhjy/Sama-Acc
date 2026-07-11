"""
Delete all business/accounting data before a legacy import.

Keeps login accounts, role groups, company branding, and (by default) the
destination catalog. Does NOT run migrations or touch media/ uploads on disk.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts_core.models import (
    Attachment,
    BookingFile,
    Client,
    CompanyBranding,
    DocumentSequence,
    Employee,
    ExchangeRate,
    Passenger,
    Supplier,
    UserProfile,
)
from auditlog.models import AuditEvent, DocumentEventLog
from catalog.models import Destination, ServiceFieldDefinition, ServiceInstance, ServiceType
from expenses.models import OperatingExpense, OperatingExpenseAttachment
from purchases.models import ExpenseCategory, SupplierBill, SupplierBillLine, SupplierJournalCredit
from sales.models import CreditNote, SalesInvoice, SalesInvoiceAttachment, SalesInvoiceLine
from treasury.models import (
    APAllocation,
    ARAllocation,
    AccountTransfer,
    MoneyAccount,
    Payment,
    ReconciliationRecord,
)

CONFIRM_PHRASE = "DELETE ALL BUSINESS DATA"


def _count(qs) -> int:
    return qs.count()


def collect_wipe_plan(*, include_destinations: bool) -> list[tuple[str, object]]:
    """Return (label, queryset) pairs in safe deletion order."""
    plan: list[tuple[str, object]] = [
        ("audit events", AuditEvent.objects.all()),
        ("document event logs", DocumentEventLog.objects.all()),
        ("AR payment allocations", ARAllocation.objects.all()),
        ("AP payment allocations", APAllocation.objects.all()),
        ("credit notes", CreditNote.objects.all()),
        ("payments", Payment.objects.all()),
        ("supplier journal credits", SupplierJournalCredit.objects.all()),
        ("supplier bill lines", SupplierBillLine.objects.all()),
        ("supplier bills", SupplierBill.objects.all()),
        ("operating expense attachments", OperatingExpenseAttachment.objects.all()),
        ("operating expenses", OperatingExpense.objects.all()),
        ("invoice attachments", SalesInvoiceAttachment.objects.all()),
        ("invoice lines", SalesInvoiceLine.objects.all()),
        ("sales invoices", SalesInvoice.objects.all()),
        ("account transfers", AccountTransfer.objects.all()),
        ("reconciliation records", ReconciliationRecord.objects.all()),
        ("money accounts", MoneyAccount.objects.all()),
        ("service instances", ServiceInstance.objects.all()),
        ("service field definitions", ServiceFieldDefinition.objects.all()),
        ("service types", ServiceType.objects.all()),
        ("booking files", BookingFile.objects.all()),
        ("passengers", Passenger.objects.all()),
        ("attachments", Attachment.objects.all()),
        ("clients", Client.objects.all()),
        ("suppliers", Supplier.objects.all()),
        ("employees", Employee.objects.all()),
        ("expense categories", ExpenseCategory.objects.all()),
        ("document sequences", DocumentSequence.objects.all()),
        ("exchange rates", ExchangeRate.objects.all()),
    ]
    if include_destinations:
        plan.append(("destinations", Destination.objects.all()))
    return plan


class Command(BaseCommand):
    help = (
        "Remove all accounting/business data (clients, invoices, payments, etc.) "
        "while keeping user logins and company branding. Use before a full legacy import."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show row counts that would be deleted; make no changes.",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            default="",
            help=f'Required to delete. Pass exactly: {CONFIRM_PHRASE}',
        )
        parser.add_argument(
            "--include-destinations",
            action="store_true",
            help="Also delete the destination catalog (default: keep destinations).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        include_destinations = options["include_destinations"]
        confirm = (options["confirm"] or "").strip()

        db = settings.DATABASES.get("default", {})
        db_name = db.get("NAME", "?")
        db_host = db.get("HOST", "localhost")

        self.stdout.write(f"Database: {db_name} @ {db_host}")
        self.stdout.write(f"DEBUG: {settings.DEBUG}")

        User = get_user_model()
        kept_users = User.objects.count()
        kept_branding = CompanyBranding.objects.count()
        kept_profiles = UserProfile.objects.count()

        plan = collect_wipe_plan(include_destinations=include_destinations)
        totals: list[tuple[str, int]] = []
        grand_total = 0
        for label, qs in plan:
            n = _count(qs)
            totals.append((label, n))
            grand_total += n

        self.stdout.write("\nRows to delete:")
        for label, n in totals:
            if n:
                self.stdout.write(f"  {label}: {n}")
        if grand_total == 0:
            self.stdout.write("  (none — database already empty of business data)")

        self.stdout.write("\nKept (not deleted):")
        self.stdout.write(f"  users: {kept_users}")
        self.stdout.write(f"  user profiles: {kept_profiles}")
        self.stdout.write(f"  company branding rows: {kept_branding}")
        if not include_destinations:
            self.stdout.write(f"  destinations: {Destination.objects.count()} (use --include-destinations to remove)")
        self.stdout.write("  auth groups / permissions (run seed_roles after import if needed)")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — no changes made."))
            return

        if confirm != CONFIRM_PHRASE:
            raise CommandError(
                f"Refusing to delete without confirmation.\n"
                f"Re-run with:\n"
                f'  python manage.py wipe_business_data --confirm "{CONFIRM_PHRASE}"'
            )

        if not settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    "\n*** PRODUCTION DATABASE *** "
                    "This permanently removes all business data listed above."
                )
            )

        deleted_total = 0
        with transaction.atomic():
            for label, qs in plan:
                n = _count(qs)
                if not n:
                    continue
                _, detail = qs.delete()
                deleted_total += n
                self.stdout.write(f"Deleted {label}: {n}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Removed {deleted_total} business rows."))
        self.stdout.write(
            "Next steps:\n"
            "  1. python manage.py seed_roles          # optional, idempotent\n"
            "  2. python manage.py import_sato26 ...   # after full backup is ready\n"
            "  3. Verify main accountant user in Admin → User profiles"
        )
