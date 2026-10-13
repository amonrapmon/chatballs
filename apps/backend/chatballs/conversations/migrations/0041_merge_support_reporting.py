"""Join report coverage boundaries with the published conversation graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0040_merge_transfer_participation_ui"),
        ("conversations", "0036_status_stop_boundary"),
        ("tenancy", "0060_merge_support_status"),
    ]
    operations = []
