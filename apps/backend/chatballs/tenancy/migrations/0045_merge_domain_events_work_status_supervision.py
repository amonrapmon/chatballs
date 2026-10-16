"""Join the domain event guards with availability and supervisor guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_domain_event_guards"),
        ("tenancy", "0044_merge_work_status_supervision"),
    ]
    operations = []
