import json

from django import forms
from django.forms import inlineformset_factory

from catalog.models import ServiceFieldDefinition, ServiceType


class ServiceTypeForm(forms.ModelForm):
    class Meta:
        model = ServiceType
        fields = ["code", "name", "requires_supplier", "default_currency"]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. TKT"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].help_text = "Short unique code (e.g. TKT, HTL)."
        self.fields["requires_supplier"].label = "Requires supplier on invoice lines"


class ServiceFieldDefinitionForm(forms.ModelForm):
    choices_text = forms.CharField(
        required=False,
        label="Choices (for Choice field type)",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "One option per line"}),
        help_text="Only used when field type is Choice.",
    )

    class Meta:
        model = ServiceFieldDefinition
        fields = ["key", "label", "field_type", "required", "order"]
        widgets = {
            "key": forms.TextInput(attrs={"placeholder": "e.g. passenger_name"}),
            "order": forms.NumberInput(attrs={"min": 1, "step": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        if not self.instance.pk and self.fields.get("field_type"):
            self.fields["field_type"].initial = ServiceFieldDefinition.FieldType.TEXT
        if self.instance.pk and self.instance.choices:
            ch = self.instance.choices
            if isinstance(ch, list):
                lines = []
                for c in ch:
                    if isinstance(c, dict):
                        lines.append(str(c.get("label") or c.get("value") or c))
                    else:
                        lines.append(str(c))
                self.fields["choices_text"].initial = "\n".join(lines)

    def clean(self):
        key = (self.data.get(self.add_prefix("key")) or "").strip()
        label = (self.data.get(self.add_prefix("label")) or "").strip()
        if not key and not label:
            return {}
        data = super().clean()
        if data.get("key") and not data.get("label"):
            self.add_error("label", "Label is required when key is set.")
        if data.get("label") and not data.get("key"):
            self.add_error("key", "Key is required when label is set.")
        raw = data.get("choices_text", "")
        choices = []
        for part in str(raw).replace(",", "\n").split("\n"):
            p = part.strip()
            if p:
                choices.append(p)
        data["choices"] = choices
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.choices = self.cleaned_data.get("choices", [])
        if commit:
            obj.save()
        return obj


class ServiceFieldDefinitionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        keys = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                continue
            key = (cd.get("key") or "").strip()
            if not key:
                continue
            if key in keys:
                raise forms.ValidationError(f"Duplicate field key: {key}")
            keys.add(key)

    def save_new(self, form, commit=True):
        cd = form.cleaned_data
        if not cd or not (cd.get("key") or "").strip():
            return None
        return super().save_new(form, commit)


ServiceFieldInlineFormSet = inlineformset_factory(
    ServiceType,
    ServiceFieldDefinition,
    form=ServiceFieldDefinitionForm,
    formset=ServiceFieldDefinitionFormSet,
    extra=1,
    can_delete=True,
    max_num=40,
)
