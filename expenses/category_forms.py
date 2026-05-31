from django import forms

from purchases.models import ExpenseCategory


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["code", "name", "is_active"]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. RENT"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].help_text = "Short unique code for reporting."
