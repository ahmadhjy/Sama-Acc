"""Load SATO26 staging JSON into Sama Accounting models."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts_core.models import Client, Employee, Supplier, UserProfile, get_default_employee_for_accounting
from catalog.models import Destination, ServiceType
from purchases.models import SupplierBillLine
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import MoneyAccount, Payment
from treasury.payment_flow import post_payment_and_allocate

LEGACY_INVOICE_PREFIX = "SATO26-SI-"
DEFAULT_DESTINATION_NAME = "Legacy import"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value[:10])


def _D(value) -> Decimal:
    return Decimal(str(value or "0"))


class Sato26Importer:
    def __init__(self, staging_dir: Path, *, user=None, dry_run: bool = False):
        self.staging_dir = staging_dir
        self.user = user or get_user_model().objects.filter(is_superuser=True).first()
        self.dry_run = dry_run
        self.stats = {
            "clients": 0,
            "suppliers": 0,
            "service_types": 0,
            "invoices": 0,
            "invoice_lines": 0,
            "supplier_bills_synced": 0,
            "supplier_bills_skipped": 0,
            "supplier_bill_errors": 0,
            "payments": 0,
            "skipped": 0,
        }
        self._clients: dict[str, Client] = {}
        self._clients_by_legacy: dict[str, Client] = {}
        self._suppliers: dict[str, Supplier] = {}
        self._service_types: dict[str, ServiceType] = {}
        self._sales_employee: Employee | None = None
        self._money_account: MoneyAccount | None = None
        self._default_destination: Destination | None = None

    def run(self, *, steps: list[str] | None = None):
        steps = steps or [
            "service_types",
            "clients",
            "suppliers",
            "setup",
            "invoices",
            "supplier_bills",
            "payments",
        ]
        if "service_types" in steps:
            self.import_service_types()
        if "clients" in steps:
            self.import_clients()
        if "suppliers" in steps:
            self.import_suppliers()
        if "setup" in steps:
            self.ensure_setup()
        if "invoices" in steps:
            self.import_invoices()
        if "supplier_bills" in steps:
            self.sync_supplier_bills()
        if "payments" in steps:
            self.import_payments()
        return self.stats

    def ensure_default_destination(self) -> Destination | None:
        if self.dry_run:
            return None
        if self._default_destination:
            return self._default_destination
        dest, _ = Destination.objects.get_or_create(
            name=DEFAULT_DESTINATION_NAME,
            defaults={"country": "", "sort_order": 9999, "is_active": True},
        )
        self._default_destination = dest
        return dest

    def _prepare_invoice_lines_for_publish(self, invoice: SalesInvoice) -> list[SalesInvoiceLine]:
        dest = self.ensure_default_destination()
        lines = list(
            invoice.lines.select_related(
                "service_type",
                "service_instance__service_type",
                "supplier",
            ).prefetch_related("service_type__field_definitions")
        )
        for line in lines:
            updates: list[str] = []
            if dest and not line.destination_id:
                line.destination = dest
                updates.append("destination")
            if self._sales_employee and not line.line_employee_id:
                line.line_employee = self._sales_employee
                updates.append("line_employee")
            if updates:
                line.save(update_fields=updates)
        return lines

    def _invoice_has_supplier_bills(self, invoice: SalesInvoice) -> bool:
        return SupplierBillLine.objects.filter(
            sales_invoice_line__invoice=invoice,
            line_kind=SupplierBillLine.LineKind.SERVICE,
        ).exists()

    def _activate_imported_invoice(self, invoice: SalesInvoice) -> tuple[bool, str]:
        """Publish invoice and create linked supplier bills (COGS)."""
        if self.dry_run:
            return True, ""

        lines = self._prepare_invoice_lines_for_publish(invoice)
        invoice.recalc_usd_amounts()
        lines = self._prepare_invoice_lines_for_publish(invoice)

        if self._invoice_has_supplier_bills(invoice) and invoice.status == SalesInvoice.Status.POSTED:
            return True, ""

        try:
            if invoice.grand_total < 0:
                if self._invoice_has_supplier_bills(invoice):
                    invoice._clear_auto_supplier_bills()
                invoice._create_posted_supplier_bills_from_lines(lines, self.user)
                if invoice.status != SalesInvoice.Status.POSTED:
                    invoice.status = SalesInvoice.Status.POSTED
                    invoice.posted_at = timezone.now()
                    invoice.posted_by = self.user
                    invoice.save(update_fields=["status", "posted_at", "posted_by"])
                return True, ""

            invoice.publish_changes(self.user)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def sync_supplier_bills(self, *, invoice_prefix: str = LEGACY_INVOICE_PREFIX):
        """Backfill supplier bills for imported invoices (safe to re-run)."""
        if not self.dry_run and not self._sales_employee:
            self.ensure_setup()

        invoices = SalesInvoice.objects.filter(invoice_no__startswith=invoice_prefix).order_by("issue_date", "invoice_no")
        for invoice in invoices:
            if self.dry_run:
                if not self._invoice_has_supplier_bills(invoice):
                    self.stats["supplier_bills_synced"] += 1
                else:
                    self.stats["supplier_bills_skipped"] += 1
                continue

            if self._invoice_has_supplier_bills(invoice):
                self.stats["supplier_bills_skipped"] += 1
                continue

            ok, err = self._activate_imported_invoice(invoice)
            if ok:
                self.stats["supplier_bills_synced"] += 1
            else:
                self.stats["supplier_bill_errors"] += 1
                self.stats.setdefault("supplier_bill_error_samples", []).append(
                    {"invoice_no": invoice.invoice_no, "error": err}
                )

    def import_service_types(self):
        for row in read_jsonl(self.staging_dir / "service_types.jsonl"):
            code = row["code"]
            if self.dry_run:
                self.stats["service_types"] += 1
                continue
            st, created = ServiceType.objects.get_or_create(
                code=code,
                defaults={
                    "name": row["name"],
                    "requires_supplier": row.get("requires_supplier", True),
                    "default_currency": row.get("default_currency", "USD"),
                    "is_active": True,
                },
            )
            if not created and st.name != row["name"]:
                st.name = row["name"]
                st.save(update_fields=["name"])
            self._service_types[code] = st
            self.stats["service_types"] += 1

    def import_clients(self):
        for row in read_jsonl(self.staging_dir / "clients.jsonl"):
            code = row["client_code"]
            if self.dry_run:
                self.stats["clients"] += 1
                continue
            defaults = {
                "name_en": row["name_en"],
                "type": row.get("type") or Client.ClientType.INDIVIDUAL,
                "phone": row.get("phone") or "",
                "email": row.get("email") or "",
                "address": row.get("address") or "",
                "notes": (row.get("notes") or "")[:2000],
            }
            if row.get("date_of_birth"):
                defaults["date_of_birth"] = _parse_date(row["date_of_birth"])
            legacy_note = f"Legacy SATO26 IDNO={row.get('legacy_id')} AccNo={row.get('legacy_acc_no')}"
            defaults["notes"] = (defaults["notes"] + "\n" + legacy_note).strip()
            client, _ = Client.objects.update_or_create(client_code=code, defaults=defaults)
            self._clients[code] = client
            if row.get("legacy_id"):
                self._clients_by_legacy[str(row["legacy_id"])] = client
            self.stats["clients"] += 1

    def import_suppliers(self):
        for row in read_jsonl(self.staging_dir / "suppliers.jsonl"):
            code = row["supplier_code"]
            if self.dry_run:
                self.stats["suppliers"] += 1
                continue
            defaults = {
                "name": row["name"],
                "type": row.get("type") or Supplier.SupplierType.OTHER,
                "managing_number": row.get("phone") or "00000000",
                "email": row.get("email") or "",
                "address": row.get("address") or "",
                "default_currency": row.get("default_currency") or "USD",
                "notes": f"Legacy SATO26 AccNo={row.get('legacy_acc_no')}",
                "is_active": True,
            }
            supplier, _ = Supplier.objects.update_or_create(supplier_code=code, defaults=defaults)
            self._suppliers[code] = supplier
            self.stats["suppliers"] += 1

    def ensure_setup(self):
        if self.dry_run:
            return

        if self.user:
            UserProfile.objects.filter(is_main_accountant=True).exclude(user=self.user).update(
                is_main_accountant=False
            )
            UserProfile.objects.update_or_create(user=self.user, defaults={"is_main_accountant": True})
            display_name = (self.user.get_full_name() or "").strip() or self.user.username
            emp = Employee.objects.filter(user=self.user, is_active=True).first()
            if not emp:
                emp, _ = Employee.objects.get_or_create(
                    user=self.user,
                    defaults={
                        "name": display_name,
                        "role": Employee.EmployeeRole.SALES,
                        "is_active": True,
                    },
                )
            elif emp.name != display_name and display_name:
                emp.name = display_name
                emp.save(update_fields=["name"])

        self._sales_employee = get_default_employee_for_accounting()
        if not self._sales_employee and self.user:
            self._sales_employee = Employee.objects.filter(user=self.user, is_active=True).first()

        MoneyAccount.objects.filter(name="SATO26 Migration Cash").update(name="Cash USD")
        self._money_account, _ = MoneyAccount.objects.get_or_create(
            name="Cash USD",
            defaults={"type": MoneyAccount.AccountType.CASH, "currency": "USD", "is_active": True},
        )

        if not self._clients:
            self._clients = {c.client_code: c for c in Client.objects.all()}
        if not self._clients_by_legacy:
            for c in Client.objects.all():
                for part in (c.notes or "").split("\n"):
                    if part.startswith("Legacy SATO26 IDNO="):
                        lid = part.split("=", 1)[1].split()[0]
                        self._clients_by_legacy[lid] = c
        if not self._suppliers:
            self._suppliers = {s.supplier_code: s for s in Supplier.objects.all()}
        if not self._service_types:
            self._service_types = {s.code: s for s in ServiceType.objects.all()}

    @transaction.atomic
    def import_invoices(self):
        if not self.dry_run and not self._sales_employee:
            self.ensure_setup()

        for row in read_jsonl(self.staging_dir / "invoices.jsonl"):
            inv_no = row["invoice_no"]
            if SalesInvoice.objects.filter(invoice_no=inv_no).exists():
                self.stats["skipped"] += 1
                continue
            if self.dry_run:
                self.stats["invoices"] += 1
                self.stats["invoice_lines"] += len(row.get("lines") or [])
                continue

            client = self._clients_by_legacy.get(str(row.get("legacy_client_id") or "")) or self._clients.get(
                row["client_code"]
            ) or Client.objects.filter(client_code=row["client_code"]).first()
            if not client:
                self.stats["skipped"] += 1
                continue

            invoice = SalesInvoice(
                invoice_no=inv_no,
                client=client,
                sales_employee=self._sales_employee,
                package_type=row.get("package_type") or "",
                issue_date=_parse_date(row.get("issue_date")),
                due_date=_parse_date(row.get("due_date")),
                currency=row.get("currency") or "USD",
                exchange_rate_to_usd=_D(row.get("exchange_rate_to_usd") or "1"),
                status=SalesInvoice.Status.DRAFT,
            )
            invoice.save()

            default_dest = self.ensure_default_destination()
            for i, line in enumerate(row.get("lines") or []):
                st = self._service_types.get(line["service_type_code"])
                if not st:
                    st = ServiceType.objects.filter(code=line["service_type_code"]).first()
                supplier = None
                if line.get("supplier_code"):
                    supplier = self._suppliers.get(line["supplier_code"]) or Supplier.objects.filter(
                        supplier_code=line["supplier_code"]
                    ).first()
                SalesInvoiceLine.objects.create(
                    invoice=invoice,
                    service_type=st,
                    supplier=supplier,
                    destination=default_dest,
                    line_employee=self._sales_employee,
                    service_date=_parse_date(line.get("service_date")),
                    qty=_D(line.get("qty") or "1"),
                    sell_price=_D(line.get("sell_price")),
                    cost_price=_D(line.get("cost_price")),
                    line_discount=_D(line.get("line_discount") or "0"),
                    line_data=line.get("line_data") or {},
                    notes=(line.get("line_notes") or line.get("description") or "")[:255],
                    sort_order=i,
                )
                self.stats["invoice_lines"] += 1

            ok, err = self._activate_imported_invoice(invoice)
            if not ok:
                self.stats.setdefault("publish_errors", []).append(
                    {"invoice_no": inv_no, "error": err}
                )
            self.stats["invoices"] += 1

    @transaction.atomic
    def import_payments(self):
        if not self.dry_run and not self._money_account:
            self.ensure_setup()

        for row in read_jsonl(self.staging_dir / "payments.jsonl"):
            receipt_no = row["receipt_no"]
            if Payment.objects.filter(receipt_no=receipt_no).exists():
                self.stats["skipped"] += 1
                continue
            if self.dry_run:
                self.stats["payments"] += 1
                continue

            payment = Payment(
                receipt_no=receipt_no,
                direction=row["direction"],
                party_type=row["party_type"],
                money_account=self._money_account,
                date=_parse_date(row.get("date")),
                currency=row.get("currency") or "USD",
                amount=_D(row.get("amount")),
                exchange_rate=_D(row.get("exchange_rate") or "1"),
                reference=row.get("reference") or "",
                note=(row.get("note") or "")[:2000],
                status=Payment.Status.DRAFT,
            )
            if row["party_type"] == Payment.PartyType.CLIENT:
                client = self._clients.get(row["client_code"]) or Client.objects.filter(
                    client_code=row["client_code"]
                ).first()
                if not client:
                    self.stats["skipped"] += 1
                    continue
                payment.client = client
            elif row["party_type"] == Payment.PartyType.SUPPLIER:
                supplier = self._suppliers.get(row["supplier_code"]) or Supplier.objects.filter(
                    supplier_code=row["supplier_code"]
                ).first()
                if not supplier:
                    self.stats["skipped"] += 1
                    continue
                payment.supplier = supplier
            else:
                payment.party_name = row.get("party_name") or "Other"
            payment.save()
            post_payment_and_allocate(payment, self.user)
            self.stats["payments"] += 1
