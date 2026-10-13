"""Объединить независимые миграции правил обработки и внутренних комментариев."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_merge_comments_participants"),
        ("conversations", "0033_handling_rules"),
    ]

    operations = []
