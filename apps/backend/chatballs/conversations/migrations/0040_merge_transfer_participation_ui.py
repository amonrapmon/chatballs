"""Join the task's history graph with the published participant UI graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0038_merge_transfer_history_main"),
        ("conversations", "0039_merge_participation_ui"),
    ]
    operations = []
