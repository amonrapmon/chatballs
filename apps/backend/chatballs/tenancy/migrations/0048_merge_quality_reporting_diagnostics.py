"""Preserve every accepted branch's tenant and immutability guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_quality_guards"),
        ("tenancy", "0044_merge_comments_diagnostics"),
        ("tenancy", "0047_work_status_block_stop"),
        ("conversations", "0037_merge_quality_reporting"),
    ]

    operations = []
