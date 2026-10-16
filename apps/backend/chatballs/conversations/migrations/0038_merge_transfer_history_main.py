"""Join participant/transfer history with the published main graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0036_merge_participant_history"),
        ("conversations", "0037_merge_assignment_policy_quality"),
    ]
    operations = []
