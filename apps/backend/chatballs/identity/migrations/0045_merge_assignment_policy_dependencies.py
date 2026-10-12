"""Join previously applied task and main membership migration histories."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0044_merge_work_status_supervision"),
        ("identity", "0044_merge_work_status_supervisor"),
    ]
    operations = []
