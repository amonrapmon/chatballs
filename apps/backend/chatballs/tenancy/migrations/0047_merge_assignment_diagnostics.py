"""Preserve both assignment and diagnostic tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0046_assignment_transfer_guards"),
        ("tenancy", "0043_turn_diagnostic_guards"),
    ]
    operations = []
