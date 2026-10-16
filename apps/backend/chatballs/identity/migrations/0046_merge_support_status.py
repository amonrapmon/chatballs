"""Preserve published availability dependencies and durable report stops."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0045_merge_assignment_policy_dependencies"),
        ("identity", "0045_work_status_stop"),
    ]
    operations = []
