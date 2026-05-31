from django import forms
from django.forms import inlineformset_factory

from purchases.models import SupplierBill, SupplierBillLine


class SupplierBillForm(forms.ModelForm):
    class Meta:
        model = SupplierBill
        fields = ["bill_no", "supplier", "bill_date", "due_date", "currency"]
        widgets = {
            "bill_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class SupplierBillLineForm(forms.ModelForm):
    class Meta:
        model = SupplierBillLine
        fields = [
            "sales_invoice_line",
            "service_instance",
            "description",
            "cost_amount",
            "notes",
        ]

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.line_kind = SupplierBillLine.LineKind.SERVICE
        obj.expense_category = None
        if commit:
            obj.save()
        return obj


SupplierBillLineFormSet = inlineformset_factory(
    SupplierBill,
    SupplierBillLine,
    form=SupplierBillLineForm,
    fields=["sales_invoice_line", "service_instance", "description", "cost_amount", "notes"],
    extra=1,
    can_delete=True,
)
