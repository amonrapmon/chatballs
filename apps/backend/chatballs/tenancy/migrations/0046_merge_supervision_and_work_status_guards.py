"""Объединить независимые миграции защиты области контроля и рабочего статуса."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0044_merge_supervisor_and_work_status"),
        ("tenancy", "0043_supervision_guards"),
        ("tenancy", "0045_merge_work_status_and_comment_guards"),
    ]

    operations = []
