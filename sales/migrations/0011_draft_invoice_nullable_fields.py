import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0008_sync_company_branding"),
        ("sales", "0010_invoice_service_type_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesinvoice",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales_invoices",
                to="accounts_core.client",
            ),
        ),
        migrations.AlterField(
            model_name="salesinvoice",
            name="sales_employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales_invoices",
                to="accounts_core.employee",
            ),
        ),
        migrations.AlterField(
            model_name="salesinvoice",
            name="issue_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
