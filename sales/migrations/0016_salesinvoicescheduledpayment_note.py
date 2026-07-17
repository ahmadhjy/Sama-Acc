from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0015_invoice_scheduled_payments"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoicescheduledpayment",
            name="note",
            field=models.TextField(blank=True, default=""),
        ),
    ]
