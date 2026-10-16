"""Join the task's existing migration history with the current main branch."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_work_status_diagnostic_guards"),
        ("tenancy", "0049_merge_availability_domain_guards"),
    ]

    operations = []
