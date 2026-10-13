"""Join task rule actions with published main migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0036_handling_rule_actions"),
        ("conversations", "0044_merge_handling_rules"),
    ]
    operations = []
