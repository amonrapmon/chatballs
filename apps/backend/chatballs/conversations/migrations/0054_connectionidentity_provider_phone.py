"""Keep observed provider phone separate from user-verified contact sharing."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0053_connector_media_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectionidentity",
            name="provider_phone",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
    ]
