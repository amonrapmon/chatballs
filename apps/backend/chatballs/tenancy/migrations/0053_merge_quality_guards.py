"""Preserve quality guards alongside the current tenant migration history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_quality_guards"),
        ("tenancy", "0052_merge_email_continuation_guards"),
        ("conversations", "0036_merge_quality_data"),
    ]
    operations = []
