"""Preserve work status guards alongside the accepted main migration graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_work_status_guards"),
        ("tenancy", "0046_merge_assistance_diagnostics"),
        ("identity", "0043_merge_work_status_participant_limit"),
    ]

    operations = []
