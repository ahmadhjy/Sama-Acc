from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_destination"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicefielddefinition",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Text"),
                    ("number", "Number"),
                    ("date", "Date"),
                    ("choice", "Choice"),
                    ("bool", "Boolean"),
                ],
                default="text",
                max_length=20,
            ),
        ),
    ]
