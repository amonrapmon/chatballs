"""Join task rule actions with published main migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0044_merge_supervisor_and_work_status"),
        ("identity", "0046_merge_support_status"),
    ]
    operations = []
