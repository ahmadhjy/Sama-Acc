import json
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from accounts_core.models import Currency
from catalog.models import Destination
from sales.models import SalesInvoice, SalesInvoiceLine


class SalesInvoiceForm(forms.ModelForm):
    invoice_no = forms.CharField(required=False)

    class Meta:
        model = SalesInvoice
        fields = [
            "invoice_no",
            "client",
            "sales_employee",
            "package_type",
            "issue_date",
            "due_date",
            "currency",
            "exchange_rate_to_usd",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "package_type": forms.Select(),
            "exchange_rate_to_usd": forms.NumberInput(attrs={"step": "0.000001", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pt = self.fields.get("package_type")
        if pt:
            pt.label = "Type of service"
            pt.required = False
            pt.empty_label = "— Select type of service —"
        self.fields["currency"].widget = forms.Select(choices=self._currency_choices())
        self.fields["exchange_rate_to_usd"].label = "Exchange rate to USD"
        self.fields["exchange_rate_to_usd"].required = False
        self.fields["exchange_rate_to_usd"].help_text = (
            "Required when currency is not USD. USD total = invoice amount × rate. Example: 1000 EUR × 1.20 = 1200 USD."
        )

    @staticmethod
    def _currency_choices():
        qs = Currency.objects.filter(is_active=True).order_by("sort_order", "code")
        if not qs.exists():
            return [("USD", "USD — US Dollar")]
        return [(c.code, f"{c.code} — {c.name}") for c in qs]

    def clean(self):
        data = super().clean()
        issue = data.get("issue_date")
        due = data.get("due_date")
        if issue and not due:
            data["due_date"] = issue
            self.cleaned_data["due_date"] = issue

        cur = (data.get("currency") or "USD").strip().upper()
        data["currency"] = cur
        self.cleaned_data["currency"] = cur

        rate = data.get("exchange_rate_to_usd")
        if cur == "USD":
            data["exchange_rate_to_usd"] = None
            self.cleaned_data["exchange_rate_to_usd"] = None
        else:
            if rate in (None, "") or (isinstance(rate, Decimal) and rate <= 0):
                self.add_error(
                    "exchange_rate_to_usd",
                    "Enter the rate to convert this currency to USD (multiply invoice amount by this rate).",
                )
        return data


class SalesInvoiceLineBaseForm(forms.ModelForm):
    """Blank rows (no service type) are allowed; filled rows are validated in clean()."""

    class Meta:
        model = SalesInvoiceLine
        fields = [
            "service_type",
            "supplier",
            "line_employee",
            "service_date",
            "destination",
            "qty",
            "sell_price",
            "cost_price",
            "line_discount",
            "notes",
            "line_data",
        ]
        widgets = {
            "line_data": forms.HiddenInput(attrs={"class": "line-data-json"}),
            "qty": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "sell_price": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "service_date": forms.DateInput(attrs={"type": "date", "class": "line-service-date"}),
            "destination": forms.Select(attrs={"class": "destination-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        dest = self.fields.get("destination")
        if dest:
            dest.queryset = Destination.objects.filter(is_active=True).order_by("sort_order", "name")
            dest.empty_label = "— Destination —"
        if not self.instance.pk:
            sd = self.fields.get("service_date")
            if sd and not self.initial.get("service_date"):
                sd.initial = timezone.localdate()

    def clean_line_data(self):
        raw = self.cleaned_data.get("line_data")
        if raw is None or raw == "":
            return {}
        if isinstance(raw, str):
            try:
                return json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON in line data.")
        return raw or {}

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("service_type"):
            return cleaned

        sell = cleaned.get("sell_price")
        if sell in (None, ""):
            cleaned["sell_price"] = Decimal("0.00")

        qty = cleaned.get("qty")
        if qty in (None, ""):
            cleaned["qty"] = Decimal("1.00")
        elif qty <= 0:
            self.add_error("qty", "Quantity must be greater than zero.")

        if cleaned.get("line_discount") in (None, ""):
            cleaned["line_discount"] = Decimal("0.00")
        if cleaned.get("cost_price") in (None, ""):
            cleaned["cost_price"] = Decimal("0.00")

        if not cleaned.get("line_employee"):
            self.add_error("line_employee", "Choose the employee responsible for this line.")

        if not cleaned.get("supplier"):
            self.add_error("supplier", "Select the supplier for this service line.")

        return cleaned


class SalesInvoiceLineForm(SalesInvoiceLineBaseForm):
    pass


class SalesInvoiceLineSalesForm(SalesInvoiceLineBaseForm):
    class Meta(SalesInvoiceLineBaseForm.Meta):
        fields = [
            "service_type",
            "supplier",
            "line_employee",
            "service_date",
            "destination",
            "qty",
            "sell_price",
            "line_discount",
            "notes",
            "line_data",
        ]


class SalesInvoiceLineInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                continue
            if cd.get("service_type"):
                active += 1
        if active < 1:
            raise ValidationError("Add at least one service line (choose a service type, price, and employee per line).")

    def save_new(self, form, commit=True):
        if form.cleaned_data and not form.cleaned_data.get("service_type"):
            return None
        return super().save_new(form, commit)


SalesInvoiceLineFormSet = inlineformset_factory(
    SalesInvoice,
    SalesInvoiceLine,
    form=SalesInvoiceLineForm,
    formset=SalesInvoiceLineInlineFormSet,
    extra=1,
    can_delete=True,
    max_num=60,
)

SalesInvoiceLineSalesFormSet = inlineformset_factory(
    SalesInvoice,
    SalesInvoiceLine,
    form=SalesInvoiceLineSalesForm,
    formset=SalesInvoiceLineInlineFormSet,
    extra=1,
    can_delete=True,
    max_num=60,
)
