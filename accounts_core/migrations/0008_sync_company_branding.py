from django.conf import settings
from django.db import migrations


def sync_branding(apps, schema_editor):
    CompanyBranding = apps.get_model("accounts_core", "CompanyBranding")
    obj, _ = CompanyBranding.objects.get_or_create(pk=1)
    updates = {
        "name": getattr(settings, "COMPANY_LEGAL_NAME", ""),
        "address": getattr(settings, "COMPANY_ADDRESS", ""),
        "phone": getattr(settings, "COMPANY_PHONE", ""),
        "email": getattr(settings, "COMPANY_EMAIL", ""),
        "footer_text": getattr(settings, "COMPANY_FOOTER_TEXT", ""),
        "default_currency": getattr(settings, "COMPANY_DEFAULT_CURRENCY", "USD"),
    }
    stale = {
        "",
        "BEIRUT HAZMIEH",
        "SAMA TOURS TRAVEL & TOURISM",
    }
    for field, value in updates.items():
        if not value:
            continue
        current = getattr(obj, field, "")
        if not current or current in stale:
            setattr(obj, field, value)
    obj.save()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts_core", "0007_companybranding"),
    ]

    operations = [
        migrations.RunPython(sync_branding, migrations.RunPython.noop),
    ]
