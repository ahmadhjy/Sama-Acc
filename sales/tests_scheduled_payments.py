from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as RequestClient
from django.test import TestCase
from django.urls import reverse

from accounts_core.models import Client, Employee
from catalog.models import Destination, ServiceType
from sales.models import SalesInvoice, SalesInvoiceLine, SalesInvoiceScheduledPayment


class InvoiceScheduledPaymentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sched1", password="test12345")
        self.client_obj = Client.objects.create(client_code="C-SCH", name_en="Schedule Client")
        self.employee = Employee.objects.create(name="Sched Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Hotel SCH", code="HTLSCH")
        self.destination = Destination.objects.create(name="Rome SCH")
        self.invoice = SalesInvoice.objects.create(
            invoice_no="INV-SCH-1",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date(2026, 7, 1),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
            grand_total=Decimal("500.00"),
            grand_total_usd=Decimal("500.00"),
        )
        SalesInvoiceLine.objects.create(
            invoice=self.invoice,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            service_date=date(2026, 7, 1),
            qty=Decimal("1"),
            sell_price=Decimal("500"),
            cost_price=Decimal("0"),
            line_discount=Decimal("0"),
            sell_price_usd=Decimal("500"),
            cost_price_usd=Decimal("0"),
        )

    def test_can_split_invoice_into_scheduled_payments(self):
        p1 = SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date(2026, 7, 10),
            amount=Decimal("200.00"),
        )
        p2 = SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date(2026, 8, 10),
            amount=Decimal("300.00"),
        )
        self.assertEqual(self.invoice.scheduled_payments.count(), 2)
        self.assertFalse(p1.is_paid)
        self.assertFalse(p2.is_paid)
        self.assertEqual(
            sum((p.amount for p in self.invoice.scheduled_payments.all()), Decimal("0")),
            Decimal("500.00"),
        )

    def test_toggle_marks_paid_and_unpaid(self):
        payment = SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date.today() - timedelta(days=1),
            amount=Decimal("200.00"),
        )
        http = RequestClient()
        http.force_login(self.user)
        url = reverse("sales:scheduled_payment_toggle", args=[payment.id])
        resp = http.post(url, {"is_paid": "1", "next": "/"})
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertTrue(payment.is_paid)
        self.assertIsNotNone(payment.paid_at)

        resp = http.post(url, {"is_paid": "0", "next": "/"})
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertFalse(payment.is_paid)
        self.assertIsNone(payment.paid_at)

    def test_scheduled_payment_list_defaults_to_unpaid(self):
        unpaid = SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date.today(),
            amount=Decimal("200.00"),
            is_paid=False,
        )
        SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("300.00"),
            is_paid=True,
        )
        http = RequestClient()
        http.force_login(self.user)
        resp = http.get(reverse("sales:scheduled_payment_list"))
        self.assertEqual(resp.status_code, 200)
        rows = resp.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], unpaid.id)
        self.assertEqual(resp.context["schedule_status"], "unpaid")

        resp_all = http.get(reverse("sales:scheduled_payment_list"), {"schedule_status": "all"})
        self.assertEqual(len(resp_all.context["rows"]), 2)

    def test_scheduled_payment_list_filters_by_due_date(self):
        SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date(2026, 7, 10),
            amount=Decimal("100.00"),
        )
        SalesInvoiceScheduledPayment.objects.create(
            invoice=self.invoice,
            due_date=date(2026, 8, 10),
            amount=Decimal("200.00"),
        )
        http = RequestClient()
        http.force_login(self.user)
        resp = http.get(
            reverse("sales:scheduled_payment_list"),
            {"schedule_status": "all", "date_from": "2026-07-01", "date_to": "2026-07-31"},
        )
        self.assertEqual(len(resp.context["rows"]), 1)
        self.assertEqual(resp.context["rows"][0]["amount"], Decimal("100.00"))
