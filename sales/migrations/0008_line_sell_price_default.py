from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0007_invoice_full_package"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesinvoiceline",
            name="sell_price",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
    ]
