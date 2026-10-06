"""Объединить независимые миграции доступа к полям и внешних инструментов."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0011_web_field_ai_access"),
        ("integrations", "0013_toolreadonlyconfirmation"),
    ]

    operations = []
