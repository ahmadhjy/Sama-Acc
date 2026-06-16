from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts_core.models import Client, Currency, Employee, Supplier
from catalog.models import Destination, ServiceInstance, ServiceType
from sales.models import SalesInvoice, SalesInvoiceLine


class ApiSmokeTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="apiuser", password="test12345")
        self.client.login(username="apiuser", password="test12345")

        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})

        self.client_obj = Client.objects.create(client_code="CAPI1", name_en="API Client")
        self.employee = Employee.objects.create(name="API Emp", role=Employee.EmployeeRole.ADMIN)
        st = ServiceType.objects.create(name="Visa", code="VISA")
        dest = Destination.objects.create(name="Dubai", country="UAE")
        sup = Supplier.objects.create(supplier_code="S-VIS", name="Visa Supplier")
        si = ServiceInstance.objects.create(service_type=st, data={"ref": "X"})
        self.invoice = SalesInvoice.objects.create(
            invoice_no="TMP-API1",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=self.invoice,
            supplier=sup,
            service_instance=si,
            line_employee=self.employee,
            destination=dest,
            qty=Decimal("1"),
            sell_price=Decimal("50"),
        )
        self.invoice.refresh_from_db()
        self.invoice.recalc_usd_amounts()

    def test_post_invoice_api_action(self):
        url = reverse("api-sales-invoices-post-doc", kwargs={"pk": self.invoice.pk})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, 200)

    def test_cannot_patch_grand_total_after_post(self):
        url = reverse("api-sales-invoices-detail", kwargs={"pk": self.invoice.pk})
        self.client.post(reverse("api-sales-invoices-post-doc", kwargs={"pk": self.invoice.pk}), format="json")
        self.invoice.refresh_from_db()
        before = self.invoice.grand_total
        response = self.client.patch(url, {"grand_total": "999.00"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.grand_total, before)
