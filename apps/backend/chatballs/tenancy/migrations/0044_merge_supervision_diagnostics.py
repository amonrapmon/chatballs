"""Keep both independent tenant guard migrations in the integrated graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_supervision_guards"),
        ("tenancy", "0043_turn_diagnostic_guards"),
    ]
    operations = []
