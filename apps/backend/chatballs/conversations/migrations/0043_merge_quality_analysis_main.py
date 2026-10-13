"""Join quality analysis cleanup with the published conversation history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0038_quality_conversation_purge"),
        ("conversations", "0042_merge_mail_support"),
    ]
    operations = []
