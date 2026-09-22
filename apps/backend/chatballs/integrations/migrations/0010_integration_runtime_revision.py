from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0009_integration_vk"),
    ]

    operations = [
        migrations.AddField(
            model_name="integration",
            name="runtime_revision",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
