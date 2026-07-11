import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class SupplierBill(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill_no = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey("accounts_core.Supplier", on_delete=models.PROTECT, related_name="supplier_bills")
    bill_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="posted_supplier_bills"
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.bill_no

    @property
    def source_sales_invoice(self):
        first_linked = (
            self.lines.select_related("sales_invoice_line__invoice")
            .filter(sales_invoice_line__invoice__isnull=False)
            .first()
        )
        if not first_linked or not first_linked.sales_invoice_line:
            return None
        return first_linked.sales_invoice_line.invoice

    @transaction.atomic
    def post(self, user):
        if self.status != self.Status.DRAFT:
            raise ValueError("Only draft bills can be posted.")
        if not self.lines.exists():
            raise ValueError("Cannot post bill without lines.")
        self.subtotal = sum([line.cost_amount for line in self.lines.all()], Decimal("0.00"))
        self.grand_total = self.subtotal
        if not self.bill_no or self.bill_no.startswith("TMP-"):
            from accounts_core.models import DocumentSequence

            self.bill_no = DocumentSequence.next_value("BILL", "BIL-", self.bill_date.year)
        self.status = self.Status.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()


class SupplierBillLine(models.Model):
    class LineKind(models.TextChoices):
        SERVICE = "SERVICE", "Service Cost (COGS)"
        OPEX = "OPEX", "Operating Expense"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill = models.ForeignKey(SupplierBill, on_delete=models.CASCADE, related_name="lines")
    sales_invoice_line = models.ForeignKey("sales.SalesInvoiceLine", null=True, blank=True, on_delete=models.SET_NULL)
    service_instance = models.ForeignKey("catalog.ServiceInstance", null=True, blank=True, on_delete=models.SET_NULL)
    file = models.ForeignKey("accounts_core.BookingFile", null=True, blank=True, on_delete=models.SET_NULL)
    line_kind = models.CharField(max_length=10, choices=LineKind.choices, default=LineKind.SERVICE)
    expense_category = models.ForeignKey("purchases.ExpenseCategory", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=255, blank=True)
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=255, blank=True)


class ExpenseCategory(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class SupplierLedgerLine(models.Model):
    """Legacy journal line on 401* supplier accounts (AP statement / trial balance parity)."""

    class DC(models.TextChoices):
        DEBIT = "D", "Debit"
        CREDIT = "C", "Credit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        "accounts_core.Supplier", on_delete=models.CASCADE, related_name="ledger_lines"
    )
    legacy_key = models.CharField(max_length=64, unique=True)
    journal_type = models.CharField(max_length=8, blank=True, default="SI")
    legacy_jvno = models.CharField(max_length=32, blank=True)
    legacy_accno = models.CharField(max_length=32, blank=True)
    line_seq = models.PositiveSmallIntegerField(default=0)
    dc = models.CharField(max_length=1, choices=DC.choices, default=DC.CREDIT)
    line_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    invoice_no = models.CharField(max_length=32, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["line_date", "journal_type", "legacy_jvno", "line_seq"]

    def __str__(self):
        return f"{self.legacy_key} {self.dc} {self.amount}"
