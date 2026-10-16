"""Include visitor observation isolation alongside all accepted tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_supervision_events_email"),
        ("tenancy", "0043_visitor_observation_guards"),
    ]
    operations = []
