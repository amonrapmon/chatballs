"""Join the 1.20 AI control version with API Connector route migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0048_conversation_ai_control_version"),
        ("conversations", "0054_connectionidentity_provider_phone"),
    ]

    operations = []
