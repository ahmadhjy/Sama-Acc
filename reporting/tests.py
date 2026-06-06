from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts_core.models import Client, Employee, Supplier
from catalog.models import Destination, ServiceInstance, ServiceType
from reporting.client_statement_rows import build_client_statement_rows
from reporting.balances import client_ar_balance, supplier_line_purchases
from reporting.supplier_statement_rows import build_supplier_statement_rows, statement_service_date_upper
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.allocation import auto_allocate_payment
from treasury.models import MoneyAccount, Payment


class ClientBalanceOverpaymentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ar1", password="test12345")
        self.client_obj = Client.objects.create(client_code="C0099", name_en="Overpay Client")
        self.employee = Employee.objects.create(name="Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Tour", code="TR")
        self.destination = Destination.objects.create(name="Paris")
        self.supplier = Supplier.objects.create(supplier_code="S-TR", name="Tour Supplier", managing_number="+33123456789")
        self.service_instance = ServiceInstance.objects.create(service_type=self.service_type, data={})
        self.account = MoneyAccount.objects.create(name="Cash USD", type=MoneyAccount.AccountType.CASH, currency="USD")

        self.invoice = SalesInvoice.objects.create(
            invoice_no="TMP-OP",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=self.invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            line_discount=Decimal("0"),
        )
        self.invoice.recalc_usd_amounts()
        self.invoice.post(self.user)

        self.payment = Payment.objects.create(
            receipt_no="TMP-PAY-OP",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("500.00"),
            status=Payment.Status.DRAFT,
        )
        self.payment.post(self.user)
        auto_allocate_payment(self.payment)

    def test_balance_negative_when_overpaid(self):
        balance = client_ar_balance(self.client_obj, date.today())
        self.assertEqual(balance, Decimal("-300.00"))

    def test_statement_running_balance_shows_credit(self):
        rows = build_client_statement_rows(self.client_obj)
        running = Decimal("0.00")
        for row in rows:
            running = running + row["debit"] - row["credit"]
        self.assertEqual(running, Decimal("-300.00"))


class SupplierStatementServiceDateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sup1", password="test12345")
        self.supplier = Supplier.objects.create(supplier_code="S-FUT", name="Future Supplier")
        self.client = Client.objects.create(client_code="C-FUT", name_en="Future Client")
        self.employee = Employee.objects.create(name="Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Ticket", code="TKF")
        self.destination = Destination.objects.create(name="London")
        self.account = MoneyAccount.objects.create(name="Cash", type=MoneyAccount.AccountType.CASH, currency="USD")
        self.future_date = date.today() + timedelta(days=30)

    def _post_invoice_with_line(self, service_date):
        inv = SalesInvoice.objects.create(
            invoice_no=f"TMP-FUT-{service_date.isoformat()}",
            client=self.client,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=service_date,
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("60"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)
        return inv

    def test_future_service_line_excluded_from_supplier_statement(self):
        self._post_invoice_with_line(self.future_date)
        rows = build_supplier_statement_rows(self.supplier)
        self.assertEqual(len(rows), 0)

    def test_future_service_line_still_in_purchases_metric(self):
        self._post_invoice_with_line(self.future_date)
        purchases = supplier_line_purchases(self.supplier, date_from=date.today(), date_to=self.future_date)
        self.assertGreater(purchases, Decimal("0"))

    def test_past_service_line_on_supplier_statement(self):
        past = date.today() - timedelta(days=5)
        self._post_invoice_with_line(past)
        rows = build_supplier_statement_rows(self.supplier)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit"], Decimal("60.00"))
        self.assertEqual(rows[0]["debit"], Decimal("0.00"))
        running = Decimal("0.00")
        for row in rows:
            running = running + row["credit"] - row["debit"]
        self.assertEqual(running, Decimal("60.00"))

    def test_statement_upper_bound_caps_future_date_to(self):
        future_to = date.today() + timedelta(days=60)
        self.assertEqual(statement_service_date_upper(future_to), date.today())
