"""Join independent guard migrations without changing their protections."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_work_status_participant_guards"),
        ("tenancy", "0043_turn_diagnostic_guards"),
    ]
    operations = []
