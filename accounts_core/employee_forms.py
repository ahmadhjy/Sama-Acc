from decimal import Decimal

from django import forms

from accounts_core.models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "first_name",
            "father_name",
            "last_name",
            "address",
            "passport_file",
            "monthly_salary",
            "role",
            "start_date",
            "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "monthly_salary": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].label = "Name"
        self.fields["father_name"].label = "Father name"
        self.fields["last_name"].label = "Last name"
        self.fields["monthly_salary"].label = "Monthly salary (USD, reference only)"
        self.fields["monthly_salary"].required = False

    def clean_monthly_salary(self):
        val = self.cleaned_data.get("monthly_salary")
        if val in (None, ""):
            return Decimal("0.00")
        return val

    def clean(self):
        data = super().clean()
        if not (data.get("first_name") or "").strip():
            self.add_error("first_name", "Name is required.")
        return data
