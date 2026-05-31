import json

from django import forms

from accounts_core.models import Client, Supplier


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "client_code",
            "type",
            "name_en",
            "name_ar",
            "date_of_birth",
            "whatsapp",
            "email",
            "address",
            "main_passport",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_of_birth"].label = "Date of birth"
        self.fields["client_code"].help_text = "Unique client code (e.g. C-0001)."


class SupplierForm(forms.ModelForm):
    phones_text = forms.CharField(
        required=False,
        label="Phone numbers",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "One number per line"}),
        help_text="Enter one phone number per line.",
    )

    class Meta:
        model = Supplier
        fields = [
            "supplier_code",
            "type",
            "name",
            "whatsapp",
            "email",
            "address",
            "default_currency",
            "terms",
            "notes",
            "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "terms": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier_code"].help_text = "Unique supplier code (e.g. S-0001)."
        if self.instance.pk and self.instance.phones:
            if isinstance(self.instance.phones, list):
                self.fields["phones_text"].initial = "\n".join(str(p) for p in self.instance.phones)

    def clean(self):
        data = super().clean()
        raw = self.cleaned_data.get("phones_text", "")
        phones = []
        for part in str(raw).replace(",", "\n").split("\n"):
            p = part.strip()
            if p:
                phones.append(p)
        data["phones"] = phones
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.phones = self.cleaned_data.get("phones", [])
        if commit:
            obj.save()
        return obj
