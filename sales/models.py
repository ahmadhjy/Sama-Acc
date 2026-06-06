import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_no = models.CharField(max_length=32, unique=True, blank=True)
    client = models.ForeignKey(
        "accounts_core.Client", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    file = models.ForeignKey(
        "accounts_core.BookingFile", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_invoices"
    )
    sales_employee = models.ForeignKey(
        "accounts_core.Employee", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    class PackageType(models.TextChoices):
        FULL_PACKAGE = "FULL_PACKAGE", "Full package"
        VISA = "VISA", "Visa"
        HOTEL = "HOTEL", "Hotel"
        TICKET = "TICKET", "Ticket"
        INSURANCE = "INSURANCE", "Insurance"
        TRANSFER = "TRANSFER", "Transfer"
        TOUR = "TOUR", "Tour"
        SECURITY = "SECURITY", "Security Approval"

    package_type = models.CharField(
        "Type of service",
        max_length=20,
        choices=PackageType.choices,
        blank=True,
        default="",
        help_text="Primary service category for this invoice (e.g. full package, ticket, hotel).",
    )
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate_to_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Multiplier to convert invoice currency to USD (USD = amount × rate). Not used when currency is USD.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posted_sales_invoices",
    )
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="voided_sales_invoices",
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    subtotal_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_total_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    grand_total_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.invoice_no or str(self.pk)

    def document_currency_is_usd(self):
        return (self.currency or "USD").upper() == "USD"

    def get_effective_rate_to_usd(self):
        """USD per 1 unit of invoice currency. Returns 1 for USD invoices."""
        if self.document_currency_is_usd():
            return Decimal("1")
        r = self.exchange_rate_to_usd
        if r is None or r <= 0:
            return None
        return r

    def total_line_cost(self):
        """Sum of (qty × cost_price) in invoice document currency."""
        if self._state.adding:
            return Decimal("0.00")
        return sum((line.qty * line.cost_price for line in self.lines.all()), Decimal("0.00"))

    def total_line_cost_usd(self):
        """Sum of (qty × cost_price_usd) for margin in USD."""
        if self._state.adding:
            return Decimal("0.00")
        return sum(
            (line.qty * (line.cost_price_usd or Decimal("0.00")) for line in self.lines.all()),
            Decimal("0.00"),
        )

    @property
    def profit_amount(self):
        """Profit in USD: selling (USD) minus line costs (USD)."""
        sell_usd = self.grand_total_usd if self.grand_total_usd is not None else Decimal("0.00")
        return sell_usd - self.total_line_cost_usd()

    def recalc_totals_from_lines(self, *, save=True):
        """Set subtotal, discount_total, and grand_total from service line selling prices."""
        if self._state.adding:
            return
        lines = list(self.lines.all())
        self.subtotal = sum(
            ((line.qty or Decimal("0")) * (line.sell_price or Decimal("0")) for line in lines),
            Decimal("0.00"),
        )
        self.discount_total = sum((line.line_discount or Decimal("0") for line in lines), Decimal("0.00"))
        self.grand_total = self.subtotal - self.discount_total
        if save:
            self.save(update_fields=["subtotal", "discount_total", "grand_total"])

    def recalc_usd_amounts(self):
        """
        Set grand_total_usd and per-line USD amounts from document currency and rate.
        Call after lines are saved (e.g. end of invoice edit view).
        """
        if not self._state.adding:
            self.recalc_totals_from_lines(save=False)
        r = self.get_effective_rate_to_usd()
        if r is None:
            return
        g = self.grand_total or Decimal("0.00")
        self.grand_total_usd = (g * r).quantize(Decimal("0.01"))
        line_updates = []
        for line in self.lines.all():
            line.sell_price_usd = ((line.sell_price or Decimal("0")) * r).quantize(Decimal("0.0001"))
            line.cost_price_usd = ((line.cost_price or Decimal("0")) * r).quantize(Decimal("0.0001"))
            line.line_discount_usd = ((line.line_discount or Decimal("0")) * r).quantize(Decimal("0.0001"))
            line_updates.append(line)
        if line_updates:
            SalesInvoiceLine.objects.bulk_update(
                line_updates, ["sell_price_usd", "cost_price_usd", "line_discount_usd"]
            )
        self.save(update_fields=["subtotal", "discount_total", "grand_total", "grand_total_usd"])

    def _create_posted_supplier_bills_from_lines(self, lines, user=None):
        """
        Create and post supplier bills from invoice service-line costs.
        One posted bill per supplier, with SERVICE lines linked back to invoice lines.
        Amounts are stored in USD on the supplier bill.
        """
        from purchases.models import SupplierBill, SupplierBillLine

        supplier_map = {}
        for line in lines:
            line_cost_usd = (line.qty or Decimal("0.00")) * (line.cost_price_usd or Decimal("0.00"))
            if line_cost_usd <= 0:
                continue
            if not line.supplier_id:
                raise ValueError("Each service line with cost must have a supplier.")
            supplier_map.setdefault(line.supplier_id, []).append((line, line_cost_usd))

        for supplier_id, supplier_lines in supplier_map.items():
            bill = SupplierBill.objects.create(
                bill_no="",
                supplier_id=supplier_id,
                bill_date=self.issue_date,
                due_date=self.issue_date,
                currency="USD",
                status=SupplierBill.Status.DRAFT,
            )
            SupplierBillLine.objects.bulk_create(
                [
                    SupplierBillLine(
                        bill=bill,
                        line_kind=SupplierBillLine.LineKind.SERVICE,
                        sales_invoice_line=line,
                        service_instance=line.service_instance,
                        file=self.file,
                        description=(line.line_summary_label() or "Service cost")[:255],
                        cost_amount=line_cost_usd,
                        notes=f"Auto-generated from sales invoice {self.invoice_no} (cost in USD).",
                    )
                    for line, line_cost_usd in supplier_lines
                ]
            )
            bill.post(user)

    def can_delete(self):
        return self.status in (self.Status.DRAFT, self.Status.VOIDED)

    def save(self, *args, **kwargs):
        if not self.issue_date:
            self.issue_date = timezone.localdate()
        if self.issue_date and self.due_date is None:
            self.due_date = self.issue_date
        if self.pk:
            existing = SalesInvoice.objects.filter(pk=self.pk).only(
                "status", "grand_total", "currency", "exchange_rate_to_usd"
            ).first()
            if existing and existing.status != self.Status.DRAFT:
                if self.grand_total != existing.grand_total:
                    raise ValueError(
                        "Cannot change the total selling price after the invoice is posted or voided."
                    )
                if (self.currency or "") != (existing.currency or ""):
                    raise ValueError("Cannot change invoice currency after the invoice is posted or voided.")
                ex = self.exchange_rate_to_usd
                ex0 = existing.exchange_rate_to_usd
                if ex != ex0 and not (ex is None and ex0 is None):
                    raise ValueError("Cannot change the exchange rate after the invoice is posted or voided.")
        super().save(*args, **kwargs)

    @transaction.atomic
    def post(self, user=None):
        if self.status != self.Status.DRAFT:
            raise ValueError("Only draft invoices can be posted.")
        if not self.client_id:
            raise ValueError("Select a client before posting.")
        if not self.sales_employee_id:
            raise ValueError("Select the sales employee before posting.")
        if not self.issue_date:
            raise ValueError("Set the issue date before posting.")
        lines = list(
            self.lines.select_related("service_type", "service_instance__service_type", "supplier").prefetch_related(
                "service_type__field_definitions"
            )
        )
        if not lines:
            raise ValueError("Cannot post invoice without lines.")
        for line in lines:
            line.validate_line_data()
        r = self.get_effective_rate_to_usd()
        if r is None:
            raise ValueError("Set the exchange rate (USD per 1 unit of invoice currency) before posting.")
        self.recalc_usd_amounts()
        lines = list(
            self.lines.select_related("service_type", "service_instance__service_type", "supplier").prefetch_related(
                "service_type__field_definitions"
            )
        )
        self.recalc_totals_from_lines(save=False)
        self.subtotal_usd = sum((line.qty * (line.sell_price_usd or Decimal("0")) for line in lines), Decimal("0.00"))
        self.discount_total_usd = sum((line.line_discount_usd or Decimal("0") for line in lines), Decimal("0.00"))
        if self.grand_total < 0:
            raise ValueError("Invoice total cannot be negative.")
        if not self.invoice_no or self.invoice_no.startswith("TMP-"):
            from accounts_core.models import DocumentSequence

            self.invoice_no = DocumentSequence.next_value("INV", "INV-", self.issue_date.year)
        self._create_posted_supplier_bills_from_lines(lines, user)
        self.status = self.Status.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()

    def void(self, user, reason):
        if self.status == self.Status.VOIDED:
            return
        if self.status == self.Status.POSTED and self.allocations.exists():
            raise ValueError("Cannot void invoice with existing allocations.")
        self.status = self.Status.VOIDED
        self.void_reason = reason
        self.voided_by = user
        self.voided_at = timezone.now()
        self.save()


class SalesInvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    service_type = models.ForeignKey(
        "catalog.ServiceType", null=True, blank=True, on_delete=models.PROTECT, related_name="invoice_lines"
    )
    service_instance = models.ForeignKey(
        "catalog.ServiceInstance", null=True, blank=True, on_delete=models.PROTECT, related_name="invoice_lines"
    )
    line_data = models.JSONField(default=dict, blank=True)
    line_employee = models.ForeignKey(
        "accounts_core.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    supplier = models.ForeignKey(
        "accounts_core.Supplier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales_invoice_lines",
    )
    service_date = models.DateField(
        null=True,
        blank=True,
        help_text="Service date for SOA/reporting; defaults to invoice issue date.",
    )
    destination = models.ForeignKey(
        "catalog.Destination",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    sell_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    line_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    sell_price_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.00"))
    cost_price_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.00"))
    line_discount_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.00"))
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.invoice_id} line"

    def effective_service_date(self):
        if self.service_date:
            return self.service_date
        if self.invoice_id:
            return self.invoice.issue_date
        return None

    def line_cost_amount_usd(self):
        return (self.qty or Decimal("0")) * (self.cost_price_usd or Decimal("0"))

    def save(self, *args, **kwargs):
        if not self.service_type_id and self.service_instance_id:
            self.service_type = self.service_instance.service_type
        if (not self.line_data) and self.service_instance_id and self.service_instance.data:
            self.line_data = dict(self.service_instance.data)
        if not self.supplier_id and self.service_instance_id and self.service_instance.supplier_id:
            self.supplier = self.service_instance.supplier
        if not self.service_date and self.invoice_id:
            issue = SalesInvoice.objects.filter(pk=self.invoice_id).values_list("issue_date", flat=True).first()
            if issue:
                self.service_date = issue
        super().save(*args, **kwargs)

    def validate_line_data(self):
        st = self.service_type
        if not st and self.service_instance_id:
            st = self.service_instance.service_type
        if not st:
            raise ValueError("Each line must have a service type.")
        data = self.line_data if isinstance(self.line_data, dict) else {}
        for fd in st.field_definitions.all():
            v = data.get(fd.key)
            empty = v is None or v == ""
            if fd.required and empty:
                raise ValueError(f'"{fd.label}" is required for service {st.name}.')
        if not self.supplier_id:
            raise ValueError(f"Select a supplier for service {st.name}.")
        if not self.line_employee_id:
            raise ValueError(f"Choose the employee responsible for service {st.name}.")
        if not self.destination_id:
            raise ValueError(f"Select a destination for service {st.name if st else 'line'}.")

    def line_selling_amount(self):
        """Selling amount for this line in invoice document currency."""
        return (self.qty or Decimal("0")) * (self.sell_price or Decimal("0")) - (self.line_discount or Decimal("0"))

    def line_selling_amount_usd(self):
        """Selling amount for this line in USD."""
        return (self.qty or Decimal("0")) * (self.sell_price_usd or Decimal("0")) - (
            self.line_discount_usd or Decimal("0")
        )

    def statement_description(self):
        """Client statement: custom service-type fields + destination."""
        st = self.service_type
        if not st and self.service_instance_id:
            st = self.service_instance.service_type
        data = self.line_data if isinstance(self.line_data, dict) else {}
        parts = []
        if st:
            for fd in st.field_definitions.all():
                val = data.get(fd.key)
                if val in (None, ""):
                    continue
                if fd.field_type == "bool":
                    parts.append("Yes" if val else "No")
                else:
                    parts.append(str(val))
        if self.destination_id and self.destination:
            parts.append(self.destination.name)
        if parts:
            return " - ".join(parts)
        return st.name if st else "Service"

    def supplier_statement_description(self):
        """Supplier statement: service type, custom fields, destination."""
        return self.statement_description()

    def line_summary_label(self):
        st = self.service_type
        if not st and self.service_instance_id:
            st = self.service_instance.service_type
        parts = [st.name if st else "Line"]
        if self.supplier_id:
            parts.append(f"Supplier: {self.supplier.name}")
        data = self.line_data if isinstance(self.line_data, dict) else {}
        for fd in (st.field_definitions.all() if st else []):
            val = data.get(fd.key)
            if val not in (None, ""):
                parts.append(f"{fd.label}: {val}")
        for k, v in data.items():
            if v in (None, ""):
                continue
            if st and any(fd.key == k for fd in st.field_definitions.all()):
                continue
            parts.append(f"{k}: {v}")
        return " — ".join(parts)


class SalesInvoiceAttachment(models.Model):
    """Multiple file attachments per sales invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="invoice_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoice_attachments"
    )

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.original_name or str(self.pk)


class CreditNote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credit_note_no = models.CharField(max_length=32, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="credit_notes")

    def __str__(self):
        return self.credit_note_no
