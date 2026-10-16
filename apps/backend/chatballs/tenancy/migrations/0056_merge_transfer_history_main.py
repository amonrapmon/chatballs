"""Join existing assignment/diagnostic guards with published tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0047_merge_assignment_diagnostics"),
        ("tenancy", "0055_merge_assignment_policy_visitor_quality"),
    ]
    operations = []
