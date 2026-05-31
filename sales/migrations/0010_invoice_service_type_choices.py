from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0009_invoice_enhancements"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesinvoice",
            name="package_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("FULL_PACKAGE", "Full package"),
                    ("VISA", "Visa"),
                    ("HOTEL", "Hotel"),
                    ("TICKET", "Ticket"),
                    ("INSURANCE", "Insurance"),
                    ("TRANSFER", "Transfer"),
                    ("TOUR", "Tour"),
                    ("SECURITY", "Security Approval"),
                ],
                default="",
                help_text="Primary service category for this invoice (e.g. full package, ticket, hotel).",
                max_length=20,
                verbose_name="Type of service",
            ),
        ),
    ]
