import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0011_alter_client_contact_person_alter_client_name_en"),
        ("purchases", "0002_expensecategory_supplierbillline_line_kind_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplierJournalCredit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("legacy_key", models.CharField(max_length=64, unique=True)),
                ("legacy_jvno", models.CharField(blank=True, max_length=32)),
                ("legacy_accno", models.CharField(blank=True, max_length=32)),
                ("line_seq", models.PositiveSmallIntegerField(default=0)),
                ("credit_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("invoice_no", models.CharField(blank=True, max_length=32)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="journal_credits",
                        to="accounts_core.supplier",
                    ),
                ),
            ],
            options={
                "ordering": ["credit_date", "legacy_jvno", "line_seq"],
            },
        ),
    ]
