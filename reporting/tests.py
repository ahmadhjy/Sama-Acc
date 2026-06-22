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


class SupplierSummaryBalanceTests(TestCase):
    def test_movement_balance_when_debit_greater(self):
        from reporting.statement_summary import _split_movement_balance_dr_cr, summarize_supplier_totals

        bal_dr, bal_cr = _split_movement_balance_dr_cr(Decimal("500"), Decimal("200"))
        self.assertEqual(bal_dr, Decimal("300"))
        self.assertEqual(bal_cr, Decimal("0"))

        rows = [
            {"tot_dr": Decimal("500"), "tot_cr": Decimal("200"), "bal_dr": Decimal("300"), "bal_cr": Decimal("0")},
        ]
        tot_dr, tot_cr, foot_bal_dr, foot_bal_cr, total_balance = summarize_supplier_totals(rows)
        self.assertEqual(tot_dr, Decimal("500"))
        self.assertEqual(tot_cr, Decimal("200"))
        self.assertEqual(foot_bal_dr, Decimal("300"))
        self.assertEqual(foot_bal_cr, Decimal("0"))
        self.assertEqual(total_balance, Decimal("300"))

    def test_movement_balance_when_credit_greater(self):
        from reporting.statement_summary import _split_movement_balance_dr_cr, summarize_supplier_totals

        bal_dr, bal_cr = _split_movement_balance_dr_cr(Decimal("150"), Decimal("400"))
        self.assertEqual(bal_dr, Decimal("0"))
        self.assertEqual(bal_cr, Decimal("250"))

        rows = [
            {"tot_dr": Decimal("100"), "tot_cr": Decimal("300"), "bal_dr": Decimal("0"), "bal_cr": Decimal("200")},
            {"tot_dr": Decimal("50"), "tot_cr": Decimal("100"), "bal_dr": Decimal("0"), "bal_cr": Decimal("50")},
        ]
        tot_dr, tot_cr, foot_bal_dr, foot_bal_cr, total_balance = summarize_supplier_totals(rows)
        self.assertEqual(tot_dr, Decimal("150"))
        self.assertEqual(tot_cr, Decimal("400"))
        self.assertEqual(foot_bal_dr, Decimal("0"))
        self.assertEqual(foot_bal_cr, Decimal("250"))
        self.assertEqual(total_balance, Decimal("250"))


class IncomeStatementPdfTests(TestCase):
    def test_profit_summary_row_shows_loss_in_debit(self):
        from reporting.statement_summary import profit_summary_row

        row = profit_summary_row("Net profit", Decimal("-150.00"))
        self.assertEqual(row["tot_dr"], Decimal("150.00"))
        self.assertEqual(row["bal_cr"], Decimal("0.00"))

    def test_prepare_income_statement_pdf_context(self):
        from accounts_core.pdf_utils import _prepare_income_statement_pdf
        from reporting.statement_summary import profit_summary_row

        context = {
            "rows": [
                {
                    "account": "4010000001",
                    "name": "Sales Revenue",
                    "curr": "USD",
                    "tot_dr": Decimal("0"),
                    "tot_cr": Decimal("1000"),
                    "bal_dr": Decimal("0"),
                    "bal_cr": Decimal("1000"),
                },
                profit_summary_row("Net profit", Decimal("200")),
            ],
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31),
            "period_label": "2026-01-01 – 2026-12-31",
            "sales_total": Decimal("1000"),
            "cogs_total": Decimal("600"),
            "gross_profit": Decimal("400"),
            "opex_total": Decimal("200"),
            "net_profit": Decimal("200"),
            "tot_dr": Decimal("600"),
            "tot_cr": Decimal("1000"),
            "bal_dr": Decimal("0"),
            "bal_cr": Decimal("400"),
            "pdf_account_range": "Accounts: 401, 501, 632",
        }
        _prepare_income_statement_pdf(context)
        self.assertEqual(len(context["pdf_stat_cards"]), 5)
        self.assertEqual(context["pdf_section_title"], "Income Statement Detail")
        self.assertIn("01/01/2026", context["pdf_section_subtitle"])
        self.assertEqual(len(context["pdf_table_rows"]), 2)
        self.assertEqual(context["pdf_table_rows"][-1]["kind"], "summary")
        self.assertEqual(context["pdf_totals"][-1][0], "Net profit")


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
        from reporting.statement_running import annotate_supplier_statement_rows

        _, _, _, closing = annotate_supplier_statement_rows(rows)
        self.assertEqual(closing, Decimal("-60.00"))

    def test_statement_rows_oldest_first(self):
        past = date.today() - timedelta(days=10)
        recent = date.today() - timedelta(days=1)
        self._post_invoice_with_line(past)
        self._post_invoice_with_line(recent)
        rows = build_supplier_statement_rows(self.supplier)
        dates = [r["date"] for r in rows if r.get("date")]
        self.assertEqual(dates, sorted(dates))
