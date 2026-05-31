from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts_core", "0005_client_date_of_birth"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplier",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
