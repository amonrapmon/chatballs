from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0045_handling_rule_guards"),
        ("tenancy", "0063_merge_quality_analysis_main"),
        ("conversations", "0044_merge_handling_rules"),
    ]
    operations = []
