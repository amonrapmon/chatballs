"""Store factual API Connector adapter acceptance separately from AI delivery."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0049_api_connector_event_transport")]

    operations = [
        migrations.AddField(
            model_name="message",
            name="connector_delivery",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
