"""Join upstream 1.22 test-conversation schema with fork media lifecycle.

Do not rewrite applied 0048..0058 Connector migrations.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0058_connector_media_multi_part"),
        ("conversations", "0050_alter_conversation_options_alter_message_options"),
    ]

    operations = []
