"""Preserve domain fact guards alongside the accepted runtime guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_domain_event_guards"),
        ("tenancy", "0046_merge_assistance_diagnostics"),
        ("tenancy", "0043_supervision_guards"),
        ("conversations", "0033_merge_domain_events_comments"),
    ]
    operations = []
