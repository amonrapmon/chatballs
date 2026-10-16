"""Объединить независимые миграции роли супервизора и рабочего статуса."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0043_merge_work_status_participant_limit"),
        ("identity", "0043_supervisor"),
    ]

    operations = []
