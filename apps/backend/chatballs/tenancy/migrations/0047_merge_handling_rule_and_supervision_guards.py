"""Объединить независимые миграции защиты правил обработки и области контроля."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0034_merge_handling_rules_and_comments"),
        ("tenancy", "0045_handling_rule_guards"),
        ("tenancy", "0046_merge_supervision_and_work_status_guards"),
    ]

    operations = []
