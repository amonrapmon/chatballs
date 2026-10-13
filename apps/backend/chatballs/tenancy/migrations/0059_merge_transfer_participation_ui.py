"""Preserve both published participant guards and the task's history graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0056_merge_transfer_history_main"),
        ("tenancy", "0058_merge_participation_ui"),
    ]
    operations = []
