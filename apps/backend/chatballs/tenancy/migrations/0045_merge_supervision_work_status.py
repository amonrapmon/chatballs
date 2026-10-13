"""Join supervision guards with the accepted comment and status guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0044_merge_work_status_supervisor"),
        ("tenancy", "0044_merge_comments_work_status"),
        ("tenancy", "0043_supervision_guards"),
    ]
    operations = []
