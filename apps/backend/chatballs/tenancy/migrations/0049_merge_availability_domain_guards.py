"""Join accepted main guards and the existing availability API branch."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_work_status_participant_guards"),
        ("tenancy", "0047_merge_domain_event_guards"),
        ("tenancy", "0048_merge_work_status_supervision"),
    ]
    operations = []
