"""Preserve both diagnostic and visitor observation tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_turn_diagnostic_guards"),
        ("tenancy", "0043_visitor_observation_guards"),
    ]

    operations = []
