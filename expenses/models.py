import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class OperatingExpense(models.Model):
    """Standalone operating costs (rent, utilities, salaries, etc.)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense_no = models.CharField(max_length=32, unique=True, blank=True)
    category = models.ForeignKey(
        "purchases.ExpenseCategory", on_delete=models.PROTECT, related_name="operating_expenses"
    )
    expense_date = models.DateField()
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate_to_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="USD = amount × rate when currency is not USD.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posted_operating_expenses",
    )
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return self.expense_no or str(self.pk)

    def recalc_usd(self):
        if (self.currency or "USD").upper() == "USD":
            self.amount_usd = (self.amount or Decimal("0")).quantize(Decimal("0.01"))
        elif self.exchange_rate_to_usd and self.exchange_rate_to_usd > 0:
            self.amount_usd = ((self.amount or Decimal("0")) * self.exchange_rate_to_usd).quantize(Decimal("0.01"))
        else:
            self.amount_usd = Decimal("0.00")

    def post(self, user=None):
        from django.utils import timezone

        if self.status != self.Status.DRAFT:
            raise ValueError("Only draft expenses can be posted.")
        if (self.currency or "USD").upper() != "USD" and not self.exchange_rate_to_usd:
            raise ValueError("Exchange rate is required for non-USD expenses.")
        self.recalc_usd()
        if not self.expense_no or self.expense_no.startswith("TMP-"):
            from accounts_core.models import DocumentSequence

            self.expense_no = DocumentSequence.next_value("OPEX", "OPEX-", self.expense_date.year)
        self.status = self.Status.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()


class OperatingExpenseAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(OperatingExpense, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="expense_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]
