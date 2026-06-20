from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient, TestCase
from django.urls import reverse

from accounts_core.models import Client, Currency, Employee, Supplier
from catalog.models import Destination, ServiceInstance, ServiceType
from purchases.models import SupplierBill
from sales.models import SalesInvoice, SalesInvoiceLine


class SalesInvoiceWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="test12345")
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C0001", name_en="Client A")
        self.employee = Employee.objects.create(name="Emp A", role=Employee.EmployeeRole.SALES)
        self.service_type = ServiceType.objects.create(name="Ticket", code="TKT")
        self.destination = Destination.objects.create(name="Dubai")
        self.supplier = Supplier.objects.create(supplier_code="S-TKT", name="Airline Supplier", managing_number="+971500000000")
        self.service_instance = ServiceInstance.objects.create(service_type=self.service_type, data={"pnr": "ABC123"})

    def test_post_invoice_calculates_totals(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-1",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("2"),
            sell_price=Decimal("100"),
            cost_price=Decimal("80"),
            line_discount=Decimal("10"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.post(self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SalesInvoice.Status.POSTED)
        self.assertEqual(invoice.subtotal, Decimal("200"))
        self.assertEqual(invoice.discount_total, Decimal("10"))
        self.assertEqual(invoice.grand_total, Decimal("190"))
        self.assertEqual(invoice.grand_total_usd, Decimal("190.00"))
        posted_bills = SupplierBill.objects.filter(supplier=self.supplier, status=SupplierBill.Status.POSTED)
        self.assertEqual(posted_bills.count(), 1)
        self.assertEqual(posted_bills.first().currency, "USD")

    def test_post_non_usd_invoice_uses_fx_for_usd_amounts(self):
        Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "is_active": True, "sort_order": 2})
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-EUR",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="EUR",
            exchange_rate_to_usd=Decimal("1.20"),
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("1000"),
            cost_price=Decimal("880"),
            line_discount=Decimal("0"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.post(self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total_usd, Decimal("1200.00"))
        bill = SupplierBill.objects.filter(supplier=self.supplier, status=SupplierBill.Status.POSTED).order_by("-created_at").first()
        self.assertIsNotNone(bill)
        self.assertEqual(bill.currency, "USD")
        self.assertEqual(bill.grand_total, Decimal("1056.00"))

    def test_cannot_post_without_lines(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-2",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        with self.assertRaises(ValueError):
            invoice.post(self.user)

    def test_cannot_post_without_client(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-NC",
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("50"),
        )
        invoice.recalc_usd_amounts()
        with self.assertRaises(ValueError) as ctx:
            invoice.post(self.user)
        self.assertIn("client", str(ctx.exception).lower())

    def test_draft_save_without_lines_or_client(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-DRAFT",
            issue_date=date.today(),
            currency="USD",
        )
        self.assertEqual(invoice.status, SalesInvoice.Status.DRAFT)
        self.assertIsNone(invoice.client_id)

    def test_can_delete_draft_and_voided_only(self):
        draft = SalesInvoice.objects.create(
            invoice_no="TMP-DEL",
            issue_date=date.today(),
            currency="USD",
        )
        self.assertTrue(draft.can_delete())
        voided = SalesInvoice.objects.create(
            invoice_no="TMP-VOID",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
            status=SalesInvoice.Status.VOIDED,
        )
        self.assertTrue(voided.can_delete())
        posted = SalesInvoice.objects.create(
            invoice_no="TMP-PST",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=posted,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("50"),
        )
        posted.recalc_usd_amounts()
        posted.post(self.user)
        self.assertFalse(posted.can_delete())

    def test_cannot_change_grand_total_after_post(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-LOCK",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            service_instance=self.service_instance,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("50"),
            line_discount=Decimal("0"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.post(self.user)
        invoice.grand_total = Decimal("99")
        with self.assertRaises(ValueError):
            invoice.save()


class InvoiceAutosaveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="autosave", password="test12345")
        self.http = HttpClient()
        self.http.login(username="autosave", password="test12345")
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C-AUTO", name_en="Auto Client")
        self.employee = Employee.objects.create(name="Auto Emp", role=Employee.EmployeeRole.SALES)
        self.service_type = ServiceType.objects.create(name="Hotel", code="HTL")
        self.destination = Destination.objects.create(name="London")
        self.supplier = Supplier.objects.create(
            supplier_code="S-AUTO", name="Auto Supplier", managing_number="+971500000001"
        )

    def _line_post_data(self, index, line_id="", sell="100.00", cost="80.00"):
        return {
            f"lines-{index}-id": line_id,
            f"lines-{index}-service_type": str(self.service_type.pk),
            f"lines-{index}-supplier": str(self.supplier.pk),
            f"lines-{index}-line_employee": str(self.employee.pk),
            f"lines-{index}-destination": str(self.destination.pk),
            f"lines-{index}-service_date": date.today().isoformat(),
            f"lines-{index}-qty": "1.00",
            f"lines-{index}-sell_price": sell,
            f"lines-{index}-cost_price": cost,
            f"lines-{index}-line_discount": "0.00",
            f"lines-{index}-notes": "",
            f"lines-{index}-line_data": "{}",
        }

    def test_autosave_twice_updates_lines_without_duplicating(self):
        payload = {
            "invoice_no": "TMP-AUTOSAVE",
            "client": str(self.client_obj.pk),
            "sales_employee": str(self.employee.pk),
            "main_destination": str(self.destination.pk),
            "package_type": "",
            "issue_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "currency": "USD",
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "60",
        }
        payload.update(self._line_post_data(0, sell="100.00", cost="70.00"))
        payload.update(self._line_post_data(1, sell="200.00", cost="150.00"))

        url = reverse("sales:invoice_autosave_new")
        first = self.http.post(url, payload)
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["line_ids_by_index"]), 2)

        invoice = SalesInvoice.objects.get(pk=data["invoice_id"])
        self.assertEqual(invoice.lines.count(), 2)

        payload["lines-INITIAL_FORMS"] = str(data["initial_forms"])
        for idx, line_id in data["line_ids_by_index"].items():
            payload[f"lines-{idx}-id"] = line_id
        payload["lines-0-sell_price"] = "110.00"
        payload["lines-1-cost_price"] = "160.00"

        second = self.http.post(
            reverse("sales:invoice_autosave", kwargs={"invoice_id": invoice.id}),
            payload,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["ok"])

        invoice.refresh_from_db()
        self.assertEqual(invoice.lines.count(), 2)
        lines = list(invoice.lines.order_by("sell_price"))
        self.assertEqual(lines[0].sell_price, Decimal("110.00"))
        self.assertEqual(lines[1].cost_price, Decimal("160.00"))
