import uuid
from decimal import Decimal

from django.db import migrations, models


def migrate_full_package_to_type(apps, schema_editor):
    SalesInvoice = apps.get_model("sales", "SalesInvoice")
    SalesInvoice.objects.filter(is_full_package=True).update(package_type="TOUR")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_destination"),
        ("sales", "0008_line_sell_price_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="package_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("VISA", "Visa"),
                    ("HOTEL", "Hotel"),
                    ("TICKET", "Ticket"),
                    ("INSURANCE", "Insurance"),
                    ("TRANSFER", "Transfer"),
                    ("TOUR", "Tour"),
                    ("SECURITY", "Security Approval"),
                ],
                default="",
                help_text="Primary package/service category for this invoice.",
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_full_package_to_type, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="salesinvoice",
            name="is_full_package",
        ),
        migrations.AddField(
            model_name="salesinvoiceline",
            name="service_date",
            field=models.DateField(
                blank=True,
                help_text="Service date for SOA/reporting; defaults to invoice issue date.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="salesinvoiceline",
            name="destination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="invoice_lines",
                to="catalog.destination",
            ),
        ),
    ]
