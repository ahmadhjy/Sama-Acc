from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts_core.models import Client, Employee, Supplier
from catalog.models import Destination, ServiceInstance, ServiceType
from reporting.client_statement_rows import build_client_statement_rows
from reporting.balances import client_ar_balance, supplier_line_purchases
from reporting.supplier_statement_rows import build_supplier_statement_rows
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
        self.assertEqual(total_balance, Decimal("-250"))


class ClientSummaryTotalsNetTests(TestCase):
    def test_footer_sums_balance_debit_and_credit_separately(self):
        from reporting.statement_summary import summarize_totals

        rows = [
            {
                "tot_dr": Decimal("100"),
                "tot_cr": Decimal("20"),
                "bal_dr": Decimal("80"),
                "bal_cr": Decimal("0"),
                "net_balance": Decimal("80"),
            },
            {
                "tot_dr": Decimal("10"),
                "tot_cr": Decimal("50"),
                "bal_dr": Decimal("0"),
                "bal_cr": Decimal("40"),
                "net_balance": Decimal("-40"),
            },
        ]
        tot_dr, tot_cr, bal_dr, bal_cr, total_balance = summarize_totals(rows)
        self.assertEqual(tot_dr, Decimal("110"))
        self.assertEqual(tot_cr, Decimal("70"))
        # Do not net: show what clients owe you AND what you owe clients.
        self.assertEqual(bal_dr, Decimal("80"))
        self.assertEqual(bal_cr, Decimal("40"))
        self.assertEqual(total_balance, Decimal("40"))


class SummaryZeroBalanceToggleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="zero-bal", password="test12345")
        self.employee = Employee.objects.create(name="ZB Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Tour ZB", code="TRZB")
        self.destination = Destination.objects.create(name="Rome")
        self.supplier = Supplier.objects.create(supplier_code="S-ZB", name="Zero Bal Supplier")
        self.client_obj = Client.objects.create(client_code="C-ZB", name_en="Zero Bal Client")
        self.account = MoneyAccount.objects.create(name="Cash ZB", type=MoneyAccount.AccountType.CASH, currency="USD")

        inv = SalesInvoice.objects.create(
            invoice_no="TMP-ZB",
            client=self.client_obj,
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
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("40"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)

        # Fully settle client so closing AR is 0; supplier cost remains unless paid.
        pay = Payment.objects.create(
            receipt_no="TMP-ZB-PAY",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("100.00"),
            status=Payment.Status.DRAFT,
        )
        pay.post(self.user)

        # Pay supplier cost so closing AP is 0.
        pay_out = Payment.objects.create(
            receipt_no="TMP-ZB-SUP-PAY",
            direction=Payment.Direction.OUT,
            party_type=Payment.PartyType.SUPPLIER,
            supplier=self.supplier,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("40.00"),
            status=Payment.Status.DRAFT,
        )
        pay_out.post(self.user)

    def test_client_zero_balance_hidden_by_default(self):
        from reporting.statement_summary import build_client_summary_rows

        hidden = build_client_summary_rows([self.client_obj])
        self.assertEqual(hidden, [])
        shown = build_client_summary_rows([self.client_obj], include_zero_balances=True)
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0]["net_balance"], Decimal("0.00"))

    def test_supplier_zero_balance_hidden_by_default(self):
        from reporting.statement_summary import build_supplier_summary_rows

        hidden = build_supplier_summary_rows([self.supplier])
        self.assertEqual(hidden, [])
        shown = build_supplier_summary_rows([self.supplier], include_zero_balances=True)
        self.assertEqual(len(shown), 1)

    def test_client_period_balance_ignores_opening(self):
        """Balance columns follow the date filter (period debit − credit), not lifetime closing."""
        from reporting.statement_summary import build_client_summary_rows

        old_client = Client.objects.create(client_code="C-PER", name_en="Period Bal Client")
        old_inv = SalesInvoice.objects.create(
            invoice_no="TMP-PER-OLD",
            client=old_client,
            sales_employee=self.employee,
            issue_date=date(2026, 6, 1),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=old_inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 6, 1),
            qty=Decimal("1"),
            sell_price=Decimal("1000"),
            cost_price=Decimal("100"),
            line_discount=Decimal("0"),
        )
        old_inv.recalc_usd_amounts()
        old_inv.post(self.user)

        new_inv = SalesInvoice.objects.create(
            invoice_no="TMP-PER-NEW",
            client=old_client,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 10),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=new_inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 7, 10),
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            cost_price=Decimal("50"),
            line_discount=Decimal("0"),
        )
        new_inv.recalc_usd_amounts()
        new_inv.post(self.user)

        # Lifetime closing would be 1200; in July–Dec period only the 200 invoice counts.
        rows = build_client_summary_rows(
            [old_client],
            date_from=date(2026, 7, 1),
            date_to=date(2026, 12, 31),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tot_dr"], Decimal("200.00"))
        self.assertEqual(rows[0]["tot_cr"], Decimal("0.00"))
        self.assertEqual(rows[0]["net_balance"], Decimal("200.00"))
        self.assertEqual(rows[0]["bal_dr"], Decimal("200.00"))
        self.assertEqual(rows[0]["bal_cr"], Decimal("0.00"))

    def test_supplier_period_balance_matches_statement_net(self):
        """All Suppliers balance = period debit − credit (same filter as supplier SOA)."""
        from reporting.statement_running import annotate_supplier_statement_rows
        from reporting.statement_summary import build_supplier_summary_rows
        from reporting.supplier_statement_rows import build_supplier_statement_rows

        sup = Supplier.objects.create(supplier_code="S-PER", name="Period Sup")
        # Cost before filter window
        old_inv = SalesInvoice.objects.create(
            invoice_no="TMP-SUP-OLD",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 6, 1),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=old_inv,
            supplier=sup,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 6, 1),
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("500"),
            line_discount=Decimal("0"),
        )
        old_inv.recalc_usd_amounts()
        old_inv.post(self.user)

        # Activity inside July–Dec
        new_inv = SalesInvoice.objects.create(
            invoice_no="TMP-SUP-NEW",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 10),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=new_inv,
            supplier=sup,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 7, 10),
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("80"),
            line_discount=Decimal("0"),
        )
        new_inv.recalc_usd_amounts()
        new_inv.post(self.user)

        date_from, date_to = date(2026, 7, 1), date(2026, 12, 31)
        stmt_rows = build_supplier_statement_rows(sup, date_from, date_to)
        _, tot_dr, tot_cr, closing = annotate_supplier_statement_rows(stmt_rows)
        summary = build_supplier_summary_rows([sup], date_from=date_from, date_to=date_to)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["tot_dr"], tot_dr)
        self.assertEqual(summary[0]["tot_cr"], tot_cr)
        self.assertEqual(summary[0]["net_balance"], closing)
        self.assertEqual(summary[0]["net_balance"], Decimal("-80.00"))
        self.assertEqual(summary[0]["bal_cr"], Decimal("80.00"))
        self.assertEqual(summary[0]["bal_dr"], Decimal("0.00"))


class InvoicePeriodPlTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pl1", password="test12345")
        self.client_obj = Client.objects.create(client_code="C-PL", name_en="PL Client")
        self.employee = Employee.objects.create(name="PL Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Hotel PL", code="HTLPL")
        self.destination = Destination.objects.create(name="Paris PL")
        self.supplier = Supplier.objects.create(supplier_code="S-PL", name="PL Supplier")

    def test_revenue_and_cogs_match_invoice_period_totals(self):
        from reporting.invoice_pl import period_cogs_usd, period_revenue_usd

        inv = SalesInvoice.objects.create(
            invoice_no="TMP-PL",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 10),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 7, 10),
            qty=Decimal("1"),
            sell_price=Decimal("3400"),
            cost_price=Decimal("3270"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)

        date_from, date_to = date(2026, 1, 1), date(2026, 12, 31)
        revenue = period_revenue_usd(date_from, date_to)
        cogs = period_cogs_usd(date_from, date_to)
        self.assertEqual(revenue, Decimal("3400.00"))
        self.assertEqual(cogs, Decimal("3270.00"))
        self.assertEqual(inv.grand_total_usd, revenue)
        self.assertEqual(inv.total_line_cost_usd(), cogs)
        self.assertEqual(revenue - cogs, Decimal("130.00"))

    def test_revenue_uses_issue_date_not_service_date(self):
        """Stats follow invoice issue date; SOA can use a different service date."""
        from reporting.invoice_pl import period_revenue_usd
        from reporting.statement_summary import period_client_soa_tot_dr_cr

        inv = SalesInvoice.objects.create(
            invoice_no="TMP-DATE",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 15),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 8, 20),
            qty=Decimal("1"),
            sell_price=Decimal("500"),
            cost_price=Decimal("200"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)

        july_from, july_to = date(2026, 7, 1), date(2026, 7, 31)
        aug_from, aug_to = date(2026, 8, 1), date(2026, 8, 31)
        self.assertEqual(period_revenue_usd(july_from, july_to), Decimal("500.00"))
        self.assertEqual(period_revenue_usd(aug_from, aug_to), Decimal("0.00"))
        soa_july, _ = period_client_soa_tot_dr_cr(july_from, july_to)
        soa_aug, _ = period_client_soa_tot_dr_cr(aug_from, aug_to)
        self.assertEqual(soa_july, Decimal("0.00"))
        self.assertEqual(soa_aug, Decimal("500.00"))

    def test_soa_footer_includes_net_zero_only_when_show_zero(self):
        """Default hides net-zero clients from footer; show-zero matches SOA activity."""
        from reporting.invoice_pl import period_revenue_usd
        from reporting.statement_summary import (
            build_client_summary_rows,
            period_client_soa_tot_dr_cr,
            summarize_totals,
        )

        settled = Client.objects.create(client_code="C-ZERO", name_en="Settled Client")
        inv = SalesInvoice.objects.create(
            invoice_no="TMP-ZERO",
            client=settled,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 5),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 7, 5),
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("10"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)
        from treasury.models import MoneyAccount, Payment

        acct = MoneyAccount.objects.create(name="Test Bank", currency="USD")
        Payment.objects.create(
            receipt_no="PAY-ZERO",
            client=settled,
            party_type=Payment.PartyType.CLIENT,
            direction=Payment.Direction.IN,
            money_account=acct,
            date=date(2026, 7, 6),
            amount=Decimal("100"),
            currency="USD",
            status=Payment.Status.POSTED,
        )

        date_from, date_to = date(2026, 1, 1), date(2026, 12, 31)
        hidden_rows = build_client_summary_rows([settled], date_from, date_to, include_zero_balances=False)
        shown_rows = build_client_summary_rows([settled], date_from, date_to, include_zero_balances=True)
        self.assertEqual(hidden_rows, [])
        self.assertEqual(len(shown_rows), 1)
        hidden_dr, _, _, _, _ = summarize_totals(hidden_rows)
        shown_dr, shown_cr, bal_dr, bal_cr, _ = summarize_totals(shown_rows)
        self.assertEqual(hidden_dr, Decimal("0.00"))
        self.assertEqual(shown_dr, Decimal("100.00"))
        self.assertEqual(shown_cr, Decimal("100.00"))
        self.assertEqual(bal_dr, Decimal("0.00"))
        self.assertEqual(bal_cr, Decimal("0.00"))
        full_dr, _ = period_client_soa_tot_dr_cr(date_from, date_to)
        self.assertEqual(shown_dr, full_dr)
        self.assertEqual(period_revenue_usd(date_from, date_to), full_dr)


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

    def test_future_service_line_shown_on_supplier_statement_until_service_date(self):
        self._post_invoice_with_line(self.future_date)
        rows = build_supplier_statement_rows(self.supplier)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit"], Decimal("60.00"))
        self.assertTrue(rows[0]["is_pending"])

    def test_future_service_line_counts_in_supplier_balance(self):
        self._post_invoice_with_line(self.future_date)
        from reporting.balances import supplier_ap_balance

        balance = supplier_ap_balance(self.supplier, date.today())
        self.assertEqual(balance, Decimal("60.00"))

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
        self.assertFalse(rows[0].get("is_pending"))
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


class SalesmanReportLineAttributionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sales1", password="test12345")
        self.client_obj = Client.objects.create(client_code="C-SR", name_en="Sales Client")
        self.emp_x = Employee.objects.create(name="Employee X", role=Employee.EmployeeRole.SALES)
        self.emp_y = Employee.objects.create(name="Employee Y", role=Employee.EmployeeRole.SALES)
        self.service_type = ServiceType.objects.create(name="Hotel", code="HTL")
        self.destination = Destination.objects.create(name="Rome")
        self.supplier = Supplier.objects.create(supplier_code="S-HTL", name="Hotel Supplier", managing_number="+390000")

    def _invoice_with_split_lines(self):
        inv = SalesInvoice.objects.create(
            invoice_no="TMP-SPLIT",
            client=self.client_obj,
            sales_employee=self.emp_x,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.emp_x,
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("40"),
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.emp_x,
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            cost_price=Decimal("80"),
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.emp_y,
            qty=Decimal("1"),
            sell_price=Decimal("500"),
            cost_price=Decimal("200"),
        )
        inv.recalc_usd_amounts()
        inv.post(self.user)
        return inv

    def test_main_salesperson_gets_only_assigned_lines(self):
        from reporting.salesman import build_brief_report, build_detailed_report

        self._invoice_with_split_lines()
        brief_x = build_brief_report(self.emp_x)
        brief_y = build_brief_report(self.emp_y)
        detailed_x = build_detailed_report(self.emp_x)
        detailed_y = build_detailed_report(self.emp_y)

        self.assertEqual(brief_x["total_revenue"], Decimal("300.00"))
        self.assertEqual(brief_x["total_cost"], Decimal("120.00"))
        self.assertEqual(brief_y["total_revenue"], Decimal("500.00"))
        self.assertEqual(brief_y["total_cost"], Decimal("200.00"))

        self.assertEqual(len(detailed_x["rows"]), 1)
        self.assertEqual(detailed_x["rows"][0]["selling"], Decimal("300.00"))
        self.assertEqual(detailed_x["rows"][0]["cost"], Decimal("120.00"))

        self.assertEqual(len(detailed_y["rows"]), 1)
        self.assertEqual(detailed_y["rows"][0]["selling"], Decimal("500.00"))
        self.assertEqual(detailed_y["rows"][0]["cost"], Decimal("200.00"))


class SupplierLedgerStatementTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(supplier_code="S-JC", name="Journal Supplier")
        self.account = MoneyAccount.objects.create(name="Cash", type=MoneyAccount.AccountType.CASH, currency="USD")
        from purchases.models import SupplierLedgerLine

        SupplierLedgerLine.objects.create(
            supplier=self.supplier,
            legacy_key="test-jc-same-day",
            journal_type="SI",
            legacy_jvno="1147",
            dc=SupplierLedgerLine.DC.CREDIT,
            line_date=date(2026, 7, 3),
            amount=Decimal("1076.00"),
            invoice_no="SATO26-SI-00440",
            description="Invoice SATO26-SI-00440",
        )
        SupplierLedgerLine.objects.create(
            supplier=self.supplier,
            legacy_key="test-pv-same-day",
            journal_type="PV",
            legacy_jvno="1158",
            dc=SupplierLedgerLine.DC.DEBIT,
            line_date=date(2026, 7, 3),
            amount=Decimal("836.00"),
            description="Payment JV 1158",
        )

    def test_ledger_lines_same_date_do_not_crash_sort(self):
        rows = build_supplier_statement_rows(self.supplier)
        self.assertEqual(len(rows), 2)
        credits = sum((r["credit"] for r in rows), Decimal("0.00"))
        debits = sum((r["debit"] for r in rows), Decimal("0.00"))
        self.assertEqual(credits, Decimal("1076.00"))
        self.assertEqual(debits, Decimal("836.00"))

    def test_live_invoice_appended_to_ledger_statement(self):
        user = get_user_model().objects.create_user(username="live-sup", password="test12345")
        client = Client.objects.create(client_code="C-LIVE-SUP", name_en="Live Client")
        employee = Employee.objects.create(name="Live Emp", role=Employee.EmployeeRole.ACCOUNTING)
        service_type = ServiceType.objects.create(name="Hotel", code="HTL-L")
        destination = Destination.objects.create(name="Beirut")
        inv = SalesInvoice.objects.create(
            invoice_no="INV-2026-00001",
            client=client,
            sales_employee=employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=inv,
            supplier=self.supplier,
            service_type=service_type,
            destination=destination,
            line_employee=employee,
            service_date=date.today(),
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            cost_price=Decimal("75"),
            line_discount=Decimal("0"),
        )
        inv.recalc_usd_amounts()
        inv.post(user)

        # Migrated invoice line replaces ledger SI credit (no double-count)
        migrated = SalesInvoice.objects.create(
            invoice_no="SATO26-SI-00440",
            client=client,
            sales_employee=employee,
            issue_date=date(2026, 7, 3),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
        )
        SalesInvoiceLine.objects.create(
            invoice=migrated,
            supplier=self.supplier,
            service_type=service_type,
            destination=destination,
            line_employee=employee,
            service_date=date(2026, 7, 3),
            qty=Decimal("1"),
            sell_price=Decimal("1000"),
            cost_price=Decimal("1076"),
            line_discount=Decimal("0"),
        )
        migrated.recalc_usd_amounts()

        rows = build_supplier_statement_rows(self.supplier)
        credits = sum((r["credit"] for r in rows), Decimal("0.00"))
        refs = {r["ref"] for r in rows}
        self.assertIn("INV-2026-00001", refs)
        self.assertIn("SATO26-SI-00440", refs)
        self.assertEqual(credits, Decimal("1151.00"))  # 1076 editable migrated + 75 live
        from reporting.balances import supplier_ap_balance

        self.assertEqual(supplier_ap_balance(self.supplier, date.today()), Decimal("315.00"))

    def test_edited_imported_invoice_cost_updates_supplier_statement(self):
        client = Client.objects.create(client_code="C-EDIT-SUP", name_en="Edit Client")
        employee = Employee.objects.create(name="Edit Emp", role=Employee.EmployeeRole.ACCOUNTING)
        service_type = ServiceType.objects.create(name="Ticket", code="TKT-E")
        destination = Destination.objects.create(name="Dubai")
        migrated = SalesInvoice.objects.create(
            invoice_no="SATO26-SI-00440",
            client=client,
            sales_employee=employee,
            issue_date=date(2026, 7, 3),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
        )
        line = SalesInvoiceLine.objects.create(
            invoice=migrated,
            supplier=self.supplier,
            service_type=service_type,
            destination=destination,
            line_employee=employee,
            service_date=date(2026, 7, 3),
            qty=Decimal("1"),
            sell_price=Decimal("1000"),
            cost_price=Decimal("1076"),
            line_discount=Decimal("0"),
        )
        migrated.recalc_usd_amounts()

        rows = build_supplier_statement_rows(self.supplier)
        purchase = next(r for r in rows if r["ref"] == "SATO26-SI-00440")
        self.assertEqual(purchase["credit"], Decimal("1076.00"))

        line.cost_price = Decimal("900")
        line.save(update_fields=["cost_price"])
        migrated.recalc_usd_amounts()

        rows = build_supplier_statement_rows(self.supplier)
        purchase = next(r for r in rows if r["ref"] == "SATO26-SI-00440")
        self.assertEqual(purchase["credit"], Decimal("900.00"))
        credits = sum((r["credit"] for r in rows), Decimal("0.00"))
        self.assertEqual(credits, Decimal("900.00"))
        from reporting.balances import supplier_ap_balance

        # Ledger PV 836 remains; editable purchase now 900 → AP 64
        self.assertEqual(supplier_ap_balance(self.supplier, date.today()), Decimal("64.00"))

    def test_ledger_si_hidden_after_line_reassigned_to_other_supplier(self):
        """Reassigning an imported line's supplier removes the stale ledger SI row."""
        other = Supplier.objects.create(supplier_code="S-EBK", name="Ebook Transfer")
        client = Client.objects.create(client_code="C-REASSIGN", name_en="Reassign Client")
        employee = Employee.objects.create(name="Reassign Emp", role=Employee.EmployeeRole.ACCOUNTING)
        service_type = ServiceType.objects.create(name="Transfer", code="TRF-R")
        destination = Destination.objects.create(name="Istanbul")
        migrated = SalesInvoice.objects.create(
            invoice_no="SATO26-SI-00440",
            client=client,
            sales_employee=employee,
            issue_date=date(2026, 7, 3),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
        )
        SalesInvoiceLine.objects.create(
            invoice=migrated,
            supplier=other,  # moved off the ledger supplier
            service_type=service_type,
            destination=destination,
            line_employee=employee,
            service_date=date(2026, 7, 3),
            qty=Decimal("1"),
            sell_price=Decimal("1200"),
            cost_price=Decimal("1076"),
            line_discount=Decimal("0"),
        )
        migrated.recalc_usd_amounts()

        old_rows = build_supplier_statement_rows(self.supplier)
        self.assertNotIn("SATO26-SI-00440", {r["ref"] for r in old_rows})

        new_rows = build_supplier_statement_rows(other)
        purchase = next(r for r in new_rows if r["ref"] == "SATO26-SI-00440")
        self.assertEqual(purchase["credit"], Decimal("1076.00"))

        from reporting.period_movements import supplier_period_movements

        movements = supplier_period_movements(supplier_ids=[self.supplier.id, other.id])
        old_dr, old_cr = movements[self.supplier.id]
        self.assertEqual(old_cr, Decimal("0.00"))  # stale SI credit gone
        _, new_cr = movements[other.id]
        self.assertEqual(new_cr, Decimal("1076.00"))

    def test_ledger_pv_links_to_imported_payment(self):
        pay = Payment.objects.create(
            receipt_no="SATO26-PV-01158",
            direction=Payment.Direction.OUT,
            party_type=Payment.PartyType.SUPPLIER,
            supplier=self.supplier,
            money_account=self.account,
            date=date(2026, 7, 3),
            currency="USD",
            amount=Decimal("836.00"),
            status=Payment.Status.POSTED,
        )
        rows = build_supplier_statement_rows(self.supplier)
        pv_row = next(r for r in rows if r["ref"] == "PV-1158")
        self.assertIsNotNone(pv_row["ref_url"])
        self.assertIn(str(pay.id), pv_row["ref_url"])

    def test_supplier_money_in_shows_as_credit(self):
        user = get_user_model().objects.create_user(username="sup-in", password="test12345")
        pay = Payment.objects.create(
            receipt_no="PAY-2026-SUP-IN",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.SUPPLIER,
            supplier=self.supplier,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("100.00"),
            status=Payment.Status.DRAFT,
        )
        pay.post(user)

        rows = build_supplier_statement_rows(self.supplier)
        receipt = next(r for r in rows if r["ref"] == "PAY-2026-SUP-IN")
        self.assertEqual(receipt["type"], "Receipt")
        self.assertEqual(receipt["credit"], Decimal("100.00"))
        self.assertEqual(receipt["debit"], Decimal("0.00"))

        from reporting.balances import supplier_ap_balance

        # Ledger: purchase 1076 - payment 836 = 240; money in +100 → AP 340
        self.assertEqual(supplier_ap_balance(self.supplier, date.today()), Decimal("340.00"))


class ClientPaymentDirectionStatementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cli-dir", password="test12345")
        self.client_obj = Client.objects.create(client_code="C-DIR", name_en="Direction Client")
        self.account = MoneyAccount.objects.create(name="Cash DIR", type=MoneyAccount.AccountType.CASH, currency="USD")

    def test_client_money_in_shows_as_credit(self):
        pay = Payment.objects.create(
            receipt_no="PAY-2026-CLI-IN",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("50.00"),
            status=Payment.Status.DRAFT,
        )
        pay.post(self.user)
        rows = build_client_statement_rows(self.client_obj)
        receipt = next(r for r in rows if r["ref"] == "PAY-2026-CLI-IN")
        self.assertEqual(receipt["credit"], Decimal("50.00"))
        self.assertEqual(receipt["debit"], Decimal("0.00"))

    def test_client_money_out_shows_as_debit(self):
        pay = Payment.objects.create(
            receipt_no="PAY-2026-CLI-OUT",
            direction=Payment.Direction.OUT,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("25.00"),
            is_refund=True,
            status=Payment.Status.DRAFT,
        )
        pay.post(self.user)
        rows = build_client_statement_rows(self.client_obj)
        refund = next(r for r in rows if r["ref"] == "PAY-2026-CLI-OUT")
        self.assertEqual(refund["debit"], Decimal("25.00"))
        self.assertEqual(refund["credit"], Decimal("0.00"))

    def test_client_statement_hides_payment_note_and_reference(self):
        pay = Payment.objects.create(
            receipt_no="PAY-2026-CLI-NOTE",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("10.00"),
            reference="internal ref text",
            note="internal note, client must not see this",
            status=Payment.Status.DRAFT,
        )
        pay.post(self.user)
        rows = build_client_statement_rows(self.client_obj)
        row = next(r for r in rows if r["ref"] == "PAY-2026-CLI-NOTE")
        self.assertEqual(row["description"], "Cash DIR")
        self.assertNotIn("internal", row["description"])

