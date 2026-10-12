"""Join independent membership availability and organization settings."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0042_organization_participant_limit"),
        ("identity", "0042_work_status"),
    ]

    operations = []
