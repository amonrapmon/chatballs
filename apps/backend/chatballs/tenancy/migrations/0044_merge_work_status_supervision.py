"""Join availability and supervisor migrations without changing data."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_work_status_participant_guards"),
        ("tenancy", "0043_supervision_guards"),
    ]
    operations = []
