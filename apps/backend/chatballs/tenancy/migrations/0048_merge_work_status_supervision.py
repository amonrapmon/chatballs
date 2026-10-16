"""Join independent availability and supervisor tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0047_merge_work_status_guards"),
        ("tenancy", "0043_supervision_guards"),
        ("identity", "0044_merge_work_status_supervisor"),
    ]

    operations = []
