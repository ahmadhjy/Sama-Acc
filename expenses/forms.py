from decimal import Decimal

from django import forms

from accounts_core.models import Currency
from expenses.models import OperatingExpense
from purchases.models import ExpenseCategory


class OperatingExpenseForm(forms.ModelForm):
    class Meta:
        model = OperatingExpense
        fields = [
            "category",
            "expense_date",
            "currency",
            "exchange_rate_to_usd",
            "amount",
            "description",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "exchange_rate_to_usd": forms.NumberInput(attrs={"step": "0.000001", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ExpenseCategory.objects.filter(is_active=True).order_by("code")
        qs = Currency.objects.filter(is_active=True).order_by("sort_order", "code")
        if qs.exists():
            self.fields["currency"].widget = forms.Select(
                choices=[(c.code, f"{c.code} — {c.name}") for c in qs]
            )
        self.fields["exchange_rate_to_usd"].label = "Exchange rate to USD"
        self.fields["exchange_rate_to_usd"].required = False

    def clean(self):
        data = super().clean()
        cur = (data.get("currency") or "USD").strip().upper()
        data["currency"] = cur
        rate = data.get("exchange_rate_to_usd")
        if cur == "USD":
            data["exchange_rate_to_usd"] = None
        elif rate in (None, "") or (isinstance(rate, Decimal) and rate <= 0):
            self.add_error("exchange_rate_to_usd", "Enter the rate to convert this currency to USD.")
        return data
