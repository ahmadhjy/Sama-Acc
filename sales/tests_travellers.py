from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as RequestClient
from django.test import TestCase
from django.urls import reverse

from accounts_core.models import Client, Employee, Supplier
from catalog.models import Destination, ServiceFieldDefinition, ServiceType
from purchases.models import SupplierLedgerLine
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.legacy_payment_sync import sync_ledger_from_payment
from treasury.models import MoneyAccount, Payment


class TravellersListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="trav1", password="test12345")
        self.client_obj = Client.objects.create(client_code="C-TRV", name_en="Traveller Client")
        self.employee = Employee.objects.create(name="Trav Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.ticket = ServiceType.objects.create(name="Ticket", code="1", requires_supplier=True)
        self.travel_fd = ServiceFieldDefinition.objects.create(
            service_type=self.ticket,
            key="1",
            label="Travel DATE",
            field_type=ServiceFieldDefinition.FieldType.DATE,
            order=1,
        )
        self.destination = Destination.objects.create(name="Sharjah")
        self.supplier = Supplier.objects.create(supplier_code="S-TRV", name="Airline")
        self.http = RequestClient()
        self.http.force_login(self.user)

    def _invoice_with_travel(self, travel_date, invoice_no="INV-TRV-1"):
        inv = SalesInvoice.objects.create(
            invoice_no=invoice_no,
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 1),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
            grand_total=Decimal("200.00"),
            grand_total_usd=Decimal("200.00"),
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            service_type=self.ticket,
            destination=self.destination,
            supplier=self.supplier,
            line_employee=self.employee,
            service_date=date(2026, 7, 1),
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            cost_price=Decimal("150"),
            line_discount=Decimal("0"),
            sell_price_usd=Decimal("200"),
            cost_price_usd=Decimal("150"),
            line_data={"1": travel_date.isoformat()},
        )
        return inv

    def test_default_shows_upcoming_only(self):
        self._invoice_with_travel(date.today() + timedelta(days=5), "INV-UP")
        self._invoice_with_travel(date.today() - timedelta(days=5), "INV-PAST")
        resp = self.http.get(reverse("sales:travellers_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["scope"], "upcoming")
        self.assertEqual(resp.context["traveller_count"], 1)
        self.assertEqual(resp.context["rows"][0]["invoice_no"], "INV-UP")
        self.assertEqual(resp.context["rows"][0]["client_name"], "Traveller Client")

    def test_all_scope_includes_past(self):
        self._invoice_with_travel(date.today() + timedelta(days=5), "INV-UP")
        self._invoice_with_travel(date.today() - timedelta(days=5), "INV-PAST")
        resp = self.http.get(reverse("sales:travellers_list"), {"scope": "all"})
        self.assertEqual(resp.context["traveller_count"], 2)


class LegacyPaymentLedgerSyncTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(supplier_code="S-LEG", name="Legacy Sup")
        self.acct = MoneyAccount.objects.create(name="Cash USD", currency="USD")

    def test_edit_imported_payment_updates_ledger_line(self):
        ledger = SupplierLedgerLine.objects.create(
            supplier=self.supplier,
            legacy_key="SATO26-SJL-PV-00042-401001-0",
            journal_type="PV",
            legacy_jvno="42",
            line_date=date(2026, 1, 10),
            amount=Decimal("100.00"),
            dc=SupplierLedgerLine.DC.DEBIT,
            description="Old",
        )
        pay = Payment.objects.create(
            receipt_no="SATO26-PV-00042",
            direction=Payment.Direction.OUT,
            party_type=Payment.PartyType.SUPPLIER,
            supplier=self.supplier,
            money_account=self.acct,
            date=date(2026, 2, 1),
            amount=Decimal("250.00"),
            currency="USD",
            status=Payment.Status.POSTED,
            note="Updated note",
        )
        sync_ledger_from_payment(pay)
        ledger.refresh_from_db()
        self.assertEqual(ledger.line_date, date(2026, 2, 1))
        self.assertEqual(ledger.amount, Decimal("250.00"))
        self.assertIn("Updated note", ledger.description)
