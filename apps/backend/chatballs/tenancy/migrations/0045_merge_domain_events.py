"""Retain all tenant protections after integrating the event journal."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_supervision_diagnostics"),
        ("tenancy", "0043_domain_event_guards"),
    ]
    operations = []
