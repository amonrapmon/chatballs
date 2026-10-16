"""Join task rule actions with published main migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0047_merge_handling_rule_and_supervision_guards"),
        ("tenancy", "0064_merge_handling_rule_guards"),
    ]
    operations = []
