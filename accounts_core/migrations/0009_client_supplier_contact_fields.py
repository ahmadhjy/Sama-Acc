from django.db import migrations, models


def copy_legacy_contact_data(apps, schema_editor):
    Client = apps.get_model("accounts_core", "Client")
    Supplier = apps.get_model("accounts_core", "Supplier")
    for client in Client.objects.all():
        if not client.phone and client.whatsapp:
            client.phone = client.whatsapp
            client.save(update_fields=["phone"])
    for supplier in Supplier.objects.all():
        updated = []
        if not supplier.managing_number and supplier.whatsapp:
            supplier.managing_number = supplier.whatsapp
            updated.append("managing_number")
        phones = supplier.phones or []
        if not supplier.accounting_number and phones:
            supplier.accounting_number = str(phones[0])
            updated.append("accounting_number")
        if not supplier.managing_number and phones:
            supplier.managing_number = str(phones[0])
            updated.append("managing_number")
        if updated:
            supplier.save(update_fields=list(set(updated)))


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0008_sync_company_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="phone",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="client",
            name="contact_person",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="client",
            name="passport_file",
            field=models.FileField(blank=True, null=True, upload_to="client_passports/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="supplier",
            name="managing_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="supplier",
            name="accounting_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.RunPython(copy_legacy_contact_data, migrations.RunPython.noop),
    ]
