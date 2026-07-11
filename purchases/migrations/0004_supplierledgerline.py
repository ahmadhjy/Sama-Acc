from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchases", "0003_supplierjournalcredit"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="SupplierJournalCredit",
            new_name="SupplierLedgerLine",
        ),
        migrations.RenameField(
            model_name="supplierledgerline",
            old_name="credit_date",
            new_name="line_date",
        ),
        migrations.AddField(
            model_name="supplierledgerline",
            name="journal_type",
            field=models.CharField(blank=True, default="SI", max_length=8),
        ),
        migrations.AddField(
            model_name="supplierledgerline",
            name="dc",
            field=models.CharField(choices=[("D", "Debit"), ("C", "Credit")], default="C", max_length=1),
        ),
        migrations.AlterField(
            model_name="supplierledgerline",
            name="amount",
            field=models.DecimalField(decimal_places=2, max_digits=14),
        ),
        migrations.AlterModelOptions(
            name="supplierledgerline",
            options={"ordering": ["line_date", "journal_type", "legacy_jvno", "line_seq"]},
        ),
        migrations.AlterField(
            model_name="supplierledgerline",
            name="supplier",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="ledger_lines",
                to="accounts_core.supplier",
            ),
        ),
    ]
