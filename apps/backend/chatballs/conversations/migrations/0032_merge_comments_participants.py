"""Keep both independently accepted histories in the migration graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0031_internal_comments"),
        ("conversations", "0031_participant_data"),
    ]

    operations = []
