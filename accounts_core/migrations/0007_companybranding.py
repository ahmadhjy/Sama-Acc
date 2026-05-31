from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0006_supplier_is_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyBranding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=255)),
                ("address", models.TextField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=120)),
                ("email", models.EmailField(blank=True, max_length=254)),
                (
                    "financial_account_number",
                    models.CharField(
                        blank=True,
                        help_text="Bank or financial account number shown on statements.",
                        max_length=64,
                    ),
                ),
                (
                    "footer_text",
                    models.TextField(
                        blank=True,
                        help_text="Optional line printed at the bottom of PDF pages.",
                    ),
                ),
                ("logo", models.ImageField(blank=True, upload_to="branding/")),
                ("default_currency", models.CharField(default="USD", max_length=8)),
            ],
            options={
                "verbose_name": "Company branding",
                "verbose_name_plural": "Company branding",
            },
        ),
    ]
