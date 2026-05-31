from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts_core.models import Client, Currency, Employee, Supplier
from catalog.models import ServiceFieldDefinition, ServiceInstance, ServiceType
from reporting.client_statement_rows import build_client_statement_rows
from sales.models import SalesInvoice, SalesInvoiceLine


class InvoiceLineTotalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="lines", password="test12345")
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.client_obj = Client.objects.create(client_code="C-LIN", name_en="Line Client")
        self.employee = Employee.objects.create(name="Emp", role=Employee.EmployeeRole.SALES)
        self.ticket = ServiceType.objects.create(name="Ticket", code="TKT2")
        ServiceFieldDefinition.objects.create(
            service_type=self.ticket,
            key="passenger",
            label="Passenger Name",
            field_type="text",
            order=1,
        )
        ServiceFieldDefinition.objects.create(
            service_type=self.ticket,
            key="dest",
            label="Destination",
            field_type="text",
            order=2,
        )
        self.hotel = ServiceType.objects.create(name="Hotel", code="HTL2")
        self.supplier = Supplier.objects.create(supplier_code="S-LIN", name="Supplier")
        self.instance = ServiceInstance.objects.create(service_type=self.ticket, data={})

    def test_grand_total_from_line_sell_prices(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-LIN",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            service_type=self.ticket,
            supplier=self.supplier,
            service_instance=self.instance,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("300"),
            line_data={"passenger": "John Doe", "dest": "Paris"},
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            service_type=self.hotel,
            supplier=self.supplier,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("200"),
        )
        invoice.recalc_totals_from_lines()
        self.assertEqual(invoice.grand_total, Decimal("500.00"))

    def test_statement_one_row_per_service_line(self):
        invoice = SalesInvoice.objects.create(
            invoice_no="TMP-ST",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            service_type=self.ticket,
            supplier=self.supplier,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("300"),
            cost_price=Decimal("100"),
            line_data={"passenger": "Jane", "dest": "Rome"},
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            service_type=self.hotel,
            supplier=self.supplier,
            line_employee=self.employee,
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            cost_price=Decimal("80"),
        )
        invoice.recalc_usd_amounts()
        invoice.post(self.user)
        rows = build_client_statement_rows(self.client_obj)
        invoice_rows = [r for r in rows if r["ref"] == invoice.invoice_no]
        self.assertEqual(len(invoice_rows), 2)
        descriptions = {r["description"] for r in invoice_rows}
        self.assertIn("Jane - Rome", descriptions)
        self.assertIn("Hotel", descriptions)
        debits = sorted(r["debit"] for r in invoice_rows)
        self.assertEqual(debits, [Decimal("200.00"), Decimal("300.00")])
