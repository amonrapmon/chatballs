"""Объединить независимые миграции защиты журнала событий и диагностики хода."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_domain_event_guards"),
        ("tenancy", "0043_turn_diagnostic_guards"),
    ]

    operations = []
