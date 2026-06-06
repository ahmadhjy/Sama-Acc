from django import forms

from accounts_core.models import Client, Supplier


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "client_code",
            "type",
            "name_en",
            "phone",
            "contact_person",
            "date_of_birth",
            "email",
            "address",
            "passport_file",
            "main_passport",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "type": forms.Select(attrs={"class": "client-type-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client_code"].help_text = "Unique client code (e.g. C-0001)."
        self.fields["name_en"].label = "Full name"
        self.fields["phone"].required = True
        self.fields["contact_person"].label = "Contact person"
        self._apply_type_ui()

    def _apply_type_ui(self):
        client_type = self.data.get("type") or self.initial.get("type") or getattr(self.instance, "type", Client.ClientType.INDIVIDUAL)
        if client_type == Client.ClientType.CORPORATE:
            self.fields["name_en"].label = "Company name"
            self.fields["contact_person"].required = True
            self.fields["date_of_birth"].widget = forms.HiddenInput()
        else:
            self.fields["contact_person"].widget = forms.HiddenInput()
            self.fields["contact_person"].required = False

    def clean(self):
        data = super().clean()
        client_type = data.get("type") or Client.ClientType.INDIVIDUAL
        phone = (data.get("phone") or "").strip()
        if not phone:
            self.add_error("phone", "Phone number is required.")
        data["phone"] = phone
        if client_type == Client.ClientType.CORPORATE:
            if not (data.get("contact_person") or "").strip():
                self.add_error("contact_person", "Contact person is required for corporate clients.")
            if not (data.get("name_en") or "").strip():
                self.add_error("name_en", "Company name is required.")
        elif not (data.get("name_en") or "").strip():
            self.add_error("name_en", "Full name is required.")
        return data


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "supplier_code",
            "type",
            "name",
            "managing_number",
            "accounting_number",
            "email",
            "address",
            "default_currency",
            "terms",
            "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "terms": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier_code"].help_text = "Unique supplier code (e.g. S-0001)."
        self.fields["managing_number"].label = "Managing number"
        self.fields["accounting_number"].label = "Accounting number"

    def clean(self):
        data = super().clean()
        managing = (data.get("managing_number") or "").strip()
        accounting = (data.get("accounting_number") or "").strip()
        data["managing_number"] = managing
        data["accounting_number"] = accounting
        if not managing and not accounting:
            raise forms.ValidationError("Enter at least one of managing number or accounting number.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.phones = [n for n in (obj.managing_number, obj.accounting_number) if n]
        if commit:
            obj.save()
        return obj
