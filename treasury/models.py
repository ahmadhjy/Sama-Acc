import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class MoneyAccount(models.Model):
    class AccountType(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=10, choices=AccountType.choices, default=AccountType.CASH)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Payment(models.Model):
    class Direction(models.TextChoices):
        IN = "IN", "In"
        OUT = "OUT", "Out"

    class PartyType(models.TextChoices):
        CLIENT = "CLIENT", "Client"
        SUPPLIER = "SUPPLIER", "Supplier"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt_no = models.CharField(max_length=32, unique=True)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    party_type = models.CharField(max_length=10, choices=PartyType.choices)
    client = models.ForeignKey("accounts_core.Client", null=True, blank=True, on_delete=models.SET_NULL)
    supplier = models.ForeignKey("accounts_core.Supplier", null=True, blank=True, on_delete=models.SET_NULL)
    party_name = models.CharField(max_length=255, blank=True, help_text="Custom party name when party type is OTHER.")
    money_account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, related_name="payments")
    payment_method = models.CharField(max_length=30, default="CASH")
    date = models.DateField()
    currency = models.CharField(max_length=3, default="USD")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.TextField(blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    attachment = models.ForeignKey("accounts_core.Attachment", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_refund = models.BooleanField(default=False)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="posted_payments"
    )
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.receipt_no

    @property
    def allocated_amount(self):
        ar = sum([x.allocated_amount for x in self.ar_allocations.all()], Decimal("0.00"))
        ap = sum([x.allocated_amount for x in self.ap_allocations.all()], Decimal("0.00"))
        return ar + ap

    @property
    def remaining_amount(self):
        return self.amount - self.allocated_amount

    def _date_as_date(self):
        from datetime import date, datetime

        d = self.date
        if isinstance(d, date) and not isinstance(d, datetime):
            return d
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, str) and d.strip():
            return datetime.strptime(d.strip()[:10], "%Y-%m-%d").date()
        raise ValueError("Payment date is missing or invalid.")

    def post(self, user=None):
        if self.status != self.Status.DRAFT:
            raise ValueError("Only draft payments can be posted.")
        if self.currency != self.money_account.currency and not self.exchange_rate:
            raise ValueError("Exchange rate is required when currencies differ.")
        if not self.receipt_no or self.receipt_no.startswith("TMP-"):
            from accounts_core.models import DocumentSequence

            pay_date = self._date_as_date()
            self.date = pay_date
            self.receipt_no = DocumentSequence.next_value("PAY", "PAY-", pay_date.year)
        self.status = self.Status.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()

    def void(self, reason):
        if self.status != self.Status.POSTED:
            raise ValueError("Only posted payments can be voided.")
        self.status = self.Status.VOIDED
        self.void_reason = reason
        self.voided_at = timezone.now()
        self.save()


class ARAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="ar_allocations")
    sales_invoice = models.ForeignKey("sales.SalesInvoice", on_delete=models.PROTECT, related_name="allocations")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.payment.direction != Payment.Direction.IN:
            raise ValueError("AR allocations require IN payment direction.")
        if self.payment.status != Payment.Status.POSTED:
            raise ValueError("Allocation requires posted payment.")
        if self.sales_invoice.status not in self.sales_invoice.reporting_statuses():
            raise ValueError("Allocation requires an active invoice.")
        if self.allocated_amount <= 0:
            raise ValueError("Allocated amount must be greater than zero.")
        if self.allocated_amount > self.payment.remaining_amount:
            raise ValueError("Allocated amount exceeds payment remaining amount.")
        allocated_total = sum([x.allocated_amount for x in self.sales_invoice.allocations.exclude(pk=self.pk)], Decimal("0.00"))
        invoice_remaining = self.sales_invoice.grand_total - allocated_total
        if self.allocated_amount > invoice_remaining:
            raise ValueError("Allocated amount exceeds invoice remaining due.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class APAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="ap_allocations")
    supplier_bill = models.ForeignKey("purchases.SupplierBill", on_delete=models.PROTECT, related_name="allocations")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.payment.direction != Payment.Direction.OUT:
            raise ValueError("AP allocations require OUT payment direction.")
        if self.payment.status != Payment.Status.POSTED:
            raise ValueError("Allocation requires posted payment.")
        if self.supplier_bill.status != self.supplier_bill.Status.POSTED:
            raise ValueError("Allocation requires posted supplier bill.")
        if self.allocated_amount <= 0:
            raise ValueError("Allocated amount must be greater than zero.")
        if self.allocated_amount > self.payment.remaining_amount:
            raise ValueError("Allocated amount exceeds payment remaining amount.")
        allocated_total = sum([x.allocated_amount for x in self.supplier_bill.allocations.exclude(pk=self.pk)], Decimal("0.00"))
        bill_remaining = self.supplier_bill.grand_total - allocated_total
        if self.allocated_amount > bill_remaining:
            raise ValueError("Allocated amount exceeds bill remaining due.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class AccountTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, related_name="transfers_out")
    to_account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, related_name="transfers_in")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    reference = models.CharField(max_length=255, blank=True)


class ReconciliationRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    money_account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, related_name="reconciliations")
    reconciliation_date = models.DateField()
    expected_closing = models.DecimalField(max_digits=14, decimal_places=2)
    physical_count = models.DecimalField(max_digits=14, decimal_places=2)
    difference = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def compute_expected_balance(cls, money_account, as_of_date):
        payment_in = (
            money_account.payments.filter(status=Payment.Status.POSTED, direction=Payment.Direction.IN, date__lte=as_of_date)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        payment_out = (
            money_account.payments.filter(status=Payment.Status.POSTED, direction=Payment.Direction.OUT, date__lte=as_of_date)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        transfer_in = (
            money_account.transfers_in.filter(date__lte=as_of_date).aggregate(total=Sum("amount")).get("total") or Decimal("0.00")
        )
        transfer_out = (
            money_account.transfers_out.filter(date__lte=as_of_date).aggregate(total=Sum("amount")).get("total")
            or Decimal("0.00")
        )
        return payment_in - payment_out + transfer_in - transfer_out
