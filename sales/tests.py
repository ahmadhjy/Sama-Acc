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

    def _create_ready_invoice(self, invoice_no="TMP-1", currency="USD", exchange_rate=None):
        invoice = SalesInvoice.objects.create(
            invoice_no=invoice_no,
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency=currency,
            exchange_rate_to_usd=exchange_rate,
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
        return invoice

    def test_publish_invoice_calculates_totals(self):
        invoice = self._create_ready_invoice()
        invoice.publish_changes(self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SalesInvoice.Status.POSTED)
        self.assertTrue(invoice.invoice_no.startswith("INV-"))
        self.assertEqual(invoice.subtotal, Decimal("200"))
        self.assertEqual(invoice.discount_total, Decimal("10"))
        self.assertEqual(invoice.grand_total, Decimal("190"))
        self.assertEqual(invoice.grand_total_usd, Decimal("190.00"))
        posted_bills = SupplierBill.objects.filter(supplier=self.supplier, status=SupplierBill.Status.POSTED)
        self.assertEqual(posted_bills.count(), 1)
        self.assertEqual(posted_bills.first().currency, "USD")

    def test_invoice_list_shows_period_totals_usd(self):
        inv_a = self._create_ready_invoice(invoice_no="TMP-LIST-A")
        inv_a.issue_date = date(2026, 7, 1)
        inv_a.save(update_fields=["issue_date"])
        inv_b = self._create_ready_invoice(invoice_no="TMP-LIST-B")
        inv_b.issue_date = date(2026, 8, 1)
        inv_b.save(update_fields=["issue_date"])
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("sales:invoice_list"),
            {"date_from": "2026-07-01", "date_to": "2026-07-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_selling_usd"], Decimal("190.00"))
        self.assertEqual(response.context["total_cost_usd"], Decimal("160.00"))
        self.assertEqual(response.context["total_profit_usd"], Decimal("30.00"))
        self.assertContains(response, "Totals for displayed invoices")

    def test_publish_non_usd_invoice_uses_fx_for_usd_amounts(self):
        Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "is_active": True, "sort_order": 2})
        invoice = self._create_ready_invoice(
            invoice_no="TMP-EUR",
            currency="EUR",
            exchange_rate=Decimal("1.20"),
        )
        SalesInvoiceLine.objects.filter(invoice=invoice).update(
            qty=Decimal("1"),
            sell_price=Decimal("1000"),
            cost_price=Decimal("880"),
            line_discount=Decimal("0"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.publish_changes(self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total_usd, Decimal("1200.00"))
        bill = SupplierBill.objects.filter(supplier=self.supplier, status=SupplierBill.Status.POSTED).order_by("-created_at").first()
        self.assertIsNotNone(bill)
        self.assertEqual(bill.currency, "USD")
        self.assertEqual(bill.grand_total, Decimal("1056.00"))

    def test_cannot_publish_without_lines(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-2",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        with self.assertRaises(ValueError):
            invoice.publish_changes(self.user)

    def test_cannot_publish_without_client(self):
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
            invoice.publish_changes(self.user)
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
        posted = self._create_ready_invoice(invoice_no="TMP-PST")
        posted.publish_changes(self.user)
        self.assertFalse(posted.can_delete())

    def test_can_edit_posted_invoice_totals(self):
        invoice = self._create_ready_invoice(invoice_no="TMP-LOCK")
        SalesInvoiceLine.objects.filter(invoice=invoice).update(
            qty=Decimal("1"),
            sell_price=Decimal("50"),
            line_discount=Decimal("0"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.publish_changes(self.user)
        invoice.grand_total = Decimal("99")
        invoice.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total, Decimal("99"))

    def test_republish_syncs_supplier_bills(self):
        invoice = self._create_ready_invoice(invoice_no="TMP-SYNC")
        SalesInvoiceLine.objects.filter(invoice=invoice).update(
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            cost_price=Decimal("50"),
            line_discount=Decimal("0"),
        )
        invoice.refresh_from_db()
        invoice.recalc_usd_amounts()
        invoice.publish_changes(self.user)
        self.assertEqual(SupplierBill.objects.filter(supplier=self.supplier).count(), 1)
        line = invoice.lines.first()
        line.cost_price = Decimal("60")
        line.save()
        invoice.recalc_usd_amounts()
        invoice.publish_changes(self.user)
        self.assertEqual(SupplierBill.objects.filter(supplier=self.supplier).count(), 1)
        bill = SupplierBill.objects.filter(supplier=self.supplier).first()
        self.assertEqual(bill.grand_total, Decimal("60.00"))


class InvoiceLineOrderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="order", password="test12345")
        self.http = HttpClient()
        self.http.login(username="order", password="test12345")
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C-ORD", name_en="Order Client")
        self.employee = Employee.objects.create(name="Order Emp", role=Employee.EmployeeRole.SALES)
        self.service_type = ServiceType.objects.create(name="Tour", code="TOR")
        self.destination = Destination.objects.create(name="Rome")
        self.supplier = Supplier.objects.create(
            supplier_code="S-ORD", name="Order Supplier", managing_number="+971500000099"
        )

    def _line_payload(self, index, sell):
        return {
            f"lines-{index}-service_type": str(self.service_type.pk),
            f"lines-{index}-supplier": str(self.supplier.pk),
            f"lines-{index}-line_employee": str(self.employee.pk),
            f"lines-{index}-destination": str(self.destination.pk),
            f"lines-{index}-service_date": date.today().isoformat(),
            f"lines-{index}-qty": "1.00",
            f"lines-{index}-sell_price": sell,
            f"lines-{index}-cost_price": "10.00",
            f"lines-{index}-line_discount": "0.00",
            f"lines-{index}-notes": f"line-{index}",
            f"lines-{index}-line_data": "{}",
        }

    def test_service_lines_keep_form_order_after_save(self):
        payload = {
            "invoice_no": "TMP-ORDER",
            "client": str(self.client_obj.pk),
            "sales_employee": str(self.employee.pk),
            "main_destination": str(self.destination.pk),
            "issue_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "currency": "USD",
            "lines-TOTAL_FORMS": "4",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "60",
        }
        for i, sell in enumerate(["100.00", "200.00", "300.00", "400.00"]):
            payload.update(self._line_payload(i, sell))

        create_resp = self.http.post(reverse("sales:invoice_create"), payload)
        self.assertEqual(create_resp.status_code, 302)
        invoice = SalesInvoice.objects.get(client=self.client_obj, sales_employee=self.employee)
        notes = list(invoice.lines.values_list("notes", flat=True))
        self.assertEqual(notes, ["line-0", "line-1", "line-2", "line-3"])

        edit_resp = self.http.get(reverse("sales:invoice_edit", kwargs={"invoice_id": invoice.id}))
        self.assertEqual(edit_resp.status_code, 200)
        content = edit_resp.content.decode()
        pos0 = content.index("line-0")
        pos1 = content.index("line-1")
        pos2 = content.index("line-2")
        pos3 = content.index("line-3")
        self.assertTrue(pos0 < pos1 < pos2 < pos3)

    def test_posted_invoice_can_be_edited(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-EDIT",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
            status=SalesInvoice.Status.POSTED,
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            supplier=self.supplier,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("50"),
        )
        resp = self.http.get(reverse("sales:invoice_edit", kwargs={"invoice_id": invoice.id}))
        self.assertEqual(resp.status_code, 200)


class InvoiceServiceDateDefaultsTests(TestCase):
    def setUp(self):
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C-SD", name_en="Service Date Client")
        self.employee = Employee.objects.create(name="SD Emp", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Visa SD", code="VISD")
        self.destination = Destination.objects.create(name="Dubai SD")
        self.supplier = Supplier.objects.create(supplier_code="S-SD", name="SD Supplier")

    def test_blank_service_date_defaults_to_invoice_issue_date(self):
        from sales.forms import SalesInvoiceLineFormSet

        issue = date(2026, 3, 15)
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-SD",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=issue,
            currency="USD",
        )
        formset = SalesInvoiceLineFormSet(
            {
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "60",
                "lines-0-service_type": str(self.service_type.pk),
                "lines-0-supplier": str(self.supplier.pk),
                "lines-0-line_employee": str(self.employee.pk),
                "lines-0-destination": str(self.destination.pk),
                "lines-0-service_date": "",
                "lines-0-qty": "1.00",
                "lines-0-sell_price": "80.00",
                "lines-0-cost_price": "50.00",
                "lines-0-line_discount": "0.00",
                "lines-0-line_data": "{}",
            },
            instance=invoice,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        line = invoice.lines.get()
        self.assertEqual(line.service_date, issue)

    def test_new_line_form_initial_service_date_is_issue_date(self):
        from sales.forms import SalesInvoiceLineFormSet

        issue = date(2026, 4, 20)
        invoice = SalesInvoice(issue_date=issue, currency="USD")
        formset = SalesInvoiceLineFormSet(instance=invoice)
        self.assertEqual(formset.forms[0].fields["service_date"].initial, issue)


class StatementLineDetailsTests(TestCase):
    def setUp(self):
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C0002", name_en="Client B")
        self.employee = Employee.objects.create(name="Emp B", role=Employee.EmployeeRole.SALES)
        self.service_type = ServiceType.objects.create(name="Hotel", code="HTL")
        from catalog.models import ServiceFieldDefinition

        ServiceFieldDefinition.objects.create(
            service_type=self.service_type,
            key="guest",
            label="Guest",
            field_type=ServiceFieldDefinition.FieldType.TEXT,
        )
        self.destination = Destination.objects.create(name="Paris")

    def test_statement_line_details_excludes_destination(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-2",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        line = SalesInvoiceLine.objects.create(
            invoice=invoice,
            service_type=self.service_type,
            destination=self.destination,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("100"),
            line_data={"guest": "John Smith"},
        )
        details = line.statement_line_details()
        self.assertIn("John Smith", details)
        self.assertNotIn("Paris", details)
        combined = line.statement_description()
        self.assertIn("Paris", combined)

