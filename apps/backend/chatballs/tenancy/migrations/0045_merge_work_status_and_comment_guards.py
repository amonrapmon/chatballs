"""Объединить независимые миграции защиты рабочего статуса и комментариев."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_work_status_participant_guards"),
        ("tenancy", "0044_merge_comment_and_diagnostic_guards"),
    ]

    operations = []
