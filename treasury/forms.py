from django import forms

from treasury.models import MoneyAccount


class MoneyAccountForm(forms.ModelForm):
    class Meta:
        model = MoneyAccount
        fields = ["name", "type", "currency", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = "Unique account name (e.g. Cash USD, Bank EUR)."
