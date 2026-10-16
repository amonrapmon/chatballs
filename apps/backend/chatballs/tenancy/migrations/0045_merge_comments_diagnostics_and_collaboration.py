"""Preserve guards from both accepted migration histories."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_comments_diagnostics"),
        ("tenancy", "0044_merge_domain_events_and_supervision"),
        ("conversations", "0034_merge_comments_and_specialist_notice"),
    ]
    operations = []
