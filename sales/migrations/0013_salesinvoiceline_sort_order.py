from django.db import migrations, models


def backfill_line_sort_order(apps, schema_editor):
    SalesInvoice = apps.get_model("sales", "SalesInvoice")
    SalesInvoiceLine = apps.get_model("sales", "SalesInvoiceLine")
    for invoice in SalesInvoice.objects.all().iterator():
        for order, line in enumerate(SalesInvoiceLine.objects.filter(invoice_id=invoice.pk).order_by("id")):
            if line.sort_order != order:
                line.sort_order = order
                line.save(update_fields=["sort_order"])


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0012_salesinvoice_main_destination"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoiceline",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_line_sort_order, migrations.RunPython.noop),
    ]
