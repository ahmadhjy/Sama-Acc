import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_destination"),
        ("sales", "0011_draft_invoice_nullable_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="main_destination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoices_main",
                to="catalog.destination",
                verbose_name="Destination",
            ),
        ),
    ]
