"""Join independent guard migrations without changing their protections."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0043_merge_work_status_participant_limit"),
        ("tenancy", "0042_work_status_guards"),
        ("tenancy", "0042_participant_guards"),
    ]
    operations = []
