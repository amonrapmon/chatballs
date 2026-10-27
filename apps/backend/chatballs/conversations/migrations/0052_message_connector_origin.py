"""Record provenance for provider-observed outgoing messages without actor spoofing."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0051_alter_conversationevent_transport")]

    operations = [
        migrations.AddField(
            model_name="message",
            name="connector_origin",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
    ]
