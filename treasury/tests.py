from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts_core.models import Client, Employee, Supplier
from catalog.models import Destination, ServiceInstance, ServiceType
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import ARAllocation, MoneyAccount, Payment
from treasury.payment_flow import post_payment_and_allocate


class TreasuryAllocationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="acc", password="test12345")
        self.client_obj = Client.objects.create(client_code="C0002", name_en="Client B")
        self.employee = Employee.objects.create(name="Emp B", role=Employee.EmployeeRole.ACCOUNTING)
        self.service_type = ServiceType.objects.create(name="Hotel", code="HTL")
        self.destination = Destination.objects.create(name="Cairo", country="Egypt")
        self.supplier = Supplier.objects.create(supplier_code="S-HTL", name="Hotel Supplier")
        self.service_instance = ServiceInstance.objects.create(service_type=self.service_type, data={"voucher": "V-1"})
        self.account = MoneyAccount.objects.create(name="Cashbox USD", type=MoneyAccount.AccountType.CASH, currency="USD")

        self.invoice = SalesInvoice.objects.create(
            invoice_no="TMP-3",
            client=self.client_obj,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=self.invoice,
            supplier=self.supplier,
            service_instance=self.service_instance,
            line_employee=self.employee,
            destination=self.destination,
            qty=Decimal("1"),
            sell_price=Decimal("200"),
            line_discount=Decimal("0"),
        )
        self.invoice.refresh_from_db()
        self.invoice.recalc_usd_amounts()
        self.invoice.post(self.user)

    def test_ar_allocation_respects_invoice_due(self):
        payment = Payment.objects.create(
            receipt_no="TMP-P1",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("500"),
            status=Payment.Status.DRAFT,
        )
        payment.post(self.user)
        ARAllocation.objects.create(payment=payment, sales_invoice=self.invoice, allocated_amount=Decimal("150"))
        with self.assertRaises(ValueError):
            ARAllocation.objects.create(payment=payment, sales_invoice=self.invoice, allocated_amount=Decimal("100"))

    def test_save_posts_and_auto_allocates(self):
        payment = Payment.objects.create(
            receipt_no="TMP-P3",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("500"),
            status=Payment.Status.DRAFT,
        )
        post_payment_and_allocate(payment, self.user)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.POSTED)
        self.assertEqual(payment.allocated_amount, Decimal("200"))
        self.assertEqual(payment.remaining_amount, Decimal("300"))

    def test_edit_posted_payment_increase_reallocates(self):
        from treasury.payment_flow import sync_posted_payment_after_edit

        payment = Payment.objects.create(
            receipt_no="TMP-P-UP",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("200"),
            status=Payment.Status.DRAFT,
        )
        post_payment_and_allocate(payment, self.user)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("200"))

        payment.amount = Decimal("500")
        payment.save()
        sync_posted_payment_after_edit(payment, self.user, party_changed=False)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("200"))
        self.assertEqual(payment.remaining_amount, Decimal("300"))

    def test_edit_posted_payment_decrease_trims_allocations(self):
        from treasury.payment_flow import sync_posted_payment_after_edit

        payment = Payment.objects.create(
            receipt_no="TMP-P-DOWN",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("500"),
            status=Payment.Status.DRAFT,
        )
        post_payment_and_allocate(payment, self.user)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("200"))

        payment.amount = Decimal("100")
        payment.save()
        sync_posted_payment_after_edit(payment, self.user, party_changed=False)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("100"))
        self.assertEqual(payment.remaining_amount, Decimal("0"))

    def test_edit_posted_payment_party_change_clears_and_reallocates(self):
        from accounts_core.models import Client as ClientModel
        from treasury.payment_flow import sync_posted_payment_after_edit

        other_client = ClientModel.objects.create(client_code="C0003", name_en="Client C")
        other_invoice = SalesInvoice.objects.create(
            invoice_no="TMP-4",
            client=other_client,
            sales_employee=self.employee,
            issue_date=date.today(),
            currency="USD",
        )
        SalesInvoiceLine.objects.create(
            invoice=other_invoice,
            supplier=self.supplier,
            service_instance=self.service_instance,
            line_employee=self.employee,
            destination=self.destination,
            qty=Decimal("1"),
            sell_price=Decimal("80"),
            line_discount=Decimal("0"),
        )
        other_invoice.refresh_from_db()
        other_invoice.recalc_usd_amounts()
        other_invoice.post(self.user)

        payment = Payment.objects.create(
            receipt_no="TMP-P-PARTY",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="USD",
            amount=Decimal("500"),
            status=Payment.Status.DRAFT,
        )
        post_payment_and_allocate(payment, self.user)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("200"))

        payment.client = other_client
        payment.save()
        sync_posted_payment_after_edit(payment, self.user, party_changed=True)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("80"))
        self.assertFalse(payment.ar_allocations.filter(sales_invoice=self.invoice).exists())
        self.assertTrue(payment.ar_allocations.filter(sales_invoice=other_invoice).exists())

    def test_post_assigns_receipt_when_date_was_string(self):
        """Regression: form POST used to leave date as str and break post()."""
        payment = Payment.objects.create(
            receipt_no="TMP-PSTR",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date="2026-06-01",
            currency="USD",
            amount=Decimal("50"),
            status=Payment.Status.DRAFT,
        )
        payment.post(self.user)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.POSTED)
        self.assertTrue(payment.receipt_no.startswith("PAY-2026-"))

    def test_payment_currency_mismatch_requires_rate(self):
        payment = Payment.objects.create(
            receipt_no="TMP-P2",
            direction=Payment.Direction.IN,
            party_type=Payment.PartyType.CLIENT,
            client=self.client_obj,
            money_account=self.account,
            date=date.today(),
            currency="LBP",
            amount=Decimal("10000000"),
            status=Payment.Status.DRAFT,
        )
        with self.assertRaises(ValueError):
            payment.post(self.user)
