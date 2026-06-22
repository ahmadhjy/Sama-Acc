import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models import F


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    """Extended fields for Django auth User (incl. main accountant default)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    is_main_accountant = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile for {self.user}"

    @classmethod
    def get_main_accountant_user(cls):
        prof = cls.objects.filter(is_main_accountant=True).select_related("user").first()
        return prof.user if prof else None

class Client(TimeStampedModel):
    class ClientType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        CORPORATE = "CORPORATE", "Corporate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_code = models.CharField(max_length=32, unique=True)
    type = models.CharField(max_length=20, choices=ClientType.choices, default=ClientType.INDIVIDUAL)
    name_en = models.CharField(max_length=255, help_text="Full name (individual) or company name (corporate).")
    name_ar = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=255, blank=True, help_text="Corporate: primary contact name.")
    date_of_birth = models.DateField(null=True, blank=True)
    phones = models.JSONField(default=list, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    main_passport = models.CharField(max_length=50, blank=True)
    passport_file = models.FileField(upload_to="client_passports/%Y/%m/", null=True, blank=True)

    @property
    def display_name(self):
        return self.name_en

    def __str__(self):
        return f"{self.client_code} - {self.name_en}"

    @property
    def outstanding_receivable(self):
        """
        What this client still owes us:
        posted invoice total selling - allocations received against those invoices.
        """
        from decimal import Decimal as D

        from django.db.models import Sum

        from sales.models import SalesInvoice

        posted_invoices = self.sales_invoices.filter(status__in=SalesInvoice.reporting_statuses())
        debit = posted_invoices.aggregate(total=Sum("grand_total")).get("total") or D("0.00")
        credit = posted_invoices.aggregate(total=Sum("allocations__allocated_amount")).get("total") or D("0.00")
        return debit - credit


class Supplier(TimeStampedModel):
    class SupplierType(models.TextChoices):
        AIRLINE = "AIRLINE", "Airline"
        HOTEL = "HOTEL", "Hotel"
        DMC = "DMC", "DMC"
        VISA = "VISA", "Visa"
        INSURANCE = "INSURANCE", "Insurance"
        TRANSFER = "TRANSFER", "Transfer"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier_code = models.CharField(max_length=32, unique=True)
    type = models.CharField(max_length=20, choices=SupplierType.choices, default=SupplierType.OTHER)
    name = models.CharField(max_length=255)
    managing_number = models.CharField(max_length=50, blank=True)
    accounting_number = models.CharField(max_length=50, blank=True)
    phones = models.JSONField(default=list, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    terms = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.supplier_code} - {self.name}"

    def contact_lines(self):
        """Managing/accounting numbers for statements and exports."""
        lines = []
        if self.managing_number:
            lines.append(f"Managing Number: {self.managing_number}")
        if self.accounting_number:
            lines.append(f"Accounting Number: {self.accounting_number}")
        return lines


class Employee(TimeStampedModel):
    class EmployeeRole(models.TextChoices):
        SALES = "SALES", "Sales"
        ACCOUNTING = "ACCOUNTING", "Accounting"
        ADMIN = "ADMIN", "Admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee_profile"
    )
    name = models.CharField(max_length=255, help_text="Display name (auto-filled from name parts).")
    first_name = models.CharField(max_length=100, blank=True)
    father_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    passport_file = models.FileField(upload_to="employee_passports/%Y/%m/", null=True, blank=True)
    monthly_salary = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Monthly salary in USD; posted to operating expenses at month end.",
    )
    role = models.CharField(max_length=20, choices=EmployeeRole.choices, default=EmployeeRole.SALES)
    start_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def full_name_parts(self):
        parts = [self.first_name, self.father_name, self.last_name]
        return " ".join(p.strip() for p in parts if p and p.strip())

    def save(self, *args, **kwargs):
        composed = self.full_name_parts()
        if composed:
            self.name = composed
        elif not self.name:
            self.name = "Employee"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BookingFile(TimeStampedModel):
    class FileStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_no = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="files")
    passengers = models.ManyToManyField("Passenger", blank=True, related_name="files")
    cost_center = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=FileStatus.choices, default=FileStatus.OPEN)

    def __str__(self):
        return self.file_no


class Attachment(TimeStampedModel):
    class Category(models.TextChoices):
        PASSPORT = "PASSPORT", "Passport"
        PAYMENT_SLIP = "PAYMENT_SLIP", "Payment Slip"
        INVOICE_SCAN = "INVOICE_SCAN", "Invoice Scan"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to="attachments/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)

    def __str__(self):
        return f"{self.category} - {self.id}"


class Passenger(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="passengers")
    full_name_en = models.CharField(max_length=255)
    full_name_ar = models.CharField(max_length=255, blank=True)
    dob = models.DateField(null=True, blank=True)
    passport_number = models.CharField(max_length=64, blank=True)
    nationality = models.CharField(max_length=64, blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    passport_attachment = models.ForeignKey(Attachment, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.full_name_en


class DocumentSequence(models.Model):
    doc_type = models.CharField(max_length=20)
    prefix = models.CharField(max_length=10, default="")
    year = models.PositiveIntegerField()
    next_number = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("doc_type", "year")

    @classmethod
    @transaction.atomic
    def next_value(cls, doc_type, prefix, year):
        seq, _ = cls.objects.select_for_update().get_or_create(
            doc_type=doc_type,
            year=year,
            defaults={"prefix": prefix, "next_number": 1},
        )
        current = seq.next_number
        seq.next_number = F("next_number") + 1
        seq.save(update_fields=["next_number"])
        return f"{seq.prefix}{year}-{current:05d}"


class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate_date = models.DateField()
    rate = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        unique_together = ("from_currency", "to_currency", "rate_date")


class Currency(models.Model):
    """Currencies selectable on invoices (managed in admin)."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name_plural = "Currencies"

    def __str__(self):
        return f"{self.code} — {self.name}"


class CompanyBranding(models.Model):
    """Singleton company details for PDFs and printed documents."""

    name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    financial_account_number = models.CharField(
        max_length=64,
        blank=True,
        help_text="Bank or financial account number shown on statements.",
    )
    footer_text = models.TextField(
        blank=True,
        help_text="Optional line printed at the bottom of PDF pages.",
    )
    logo = models.ImageField(upload_to="branding/", blank=True)
    default_currency = models.CharField(max_length=8, default="USD")

    class Meta:
        verbose_name = "Company branding"
        verbose_name_plural = "Company branding"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.name or "Company"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        from django.conf import settings

        defaults = {
            "name": getattr(settings, "COMPANY_LEGAL_NAME", ""),
            "address": getattr(settings, "COMPANY_ADDRESS", ""),
            "phone": getattr(settings, "COMPANY_PHONE", ""),
            "email": getattr(settings, "COMPANY_EMAIL", ""),
            "financial_account_number": getattr(settings, "COMPANY_FINANCIAL_ACCOUNT", ""),
            "footer_text": getattr(settings, "COMPANY_FOOTER_TEXT", ""),
            "default_currency": getattr(settings, "COMPANY_DEFAULT_CURRENCY", "USD"),
        }
        obj, _ = cls.objects.get_or_create(pk=1, defaults=defaults)
        return obj


def get_default_employee_for_accounting():
    """Prefer main accountant's Employee, else first active accounting employee."""
    user = UserProfile.get_main_accountant_user()
    if user:
        emp = Employee.objects.filter(user=user, is_active=True).first()
        if emp:
            return emp
    return Employee.objects.filter(role=Employee.EmployeeRole.ACCOUNTING, is_active=True).first()
