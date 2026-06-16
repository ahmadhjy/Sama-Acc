from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0009_client_supplier_contact_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="father_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="employee",
            name="first_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="employee",
            name="last_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="employee",
            name="monthly_salary",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Monthly salary in USD; posted to operating expenses at month end.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="passport_file",
            field=models.FileField(blank=True, null=True, upload_to="employee_passports/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="employee",
            name="name",
            field=models.CharField(help_text="Display name (auto-filled from name parts).", max_length=255),
        ),
    ]
