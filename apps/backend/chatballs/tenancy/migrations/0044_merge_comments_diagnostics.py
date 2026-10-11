"""Preserve internal-history and diagnostic tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_comments_participants"),
        ("tenancy", "0043_turn_diagnostic_guards"),
    ]

    operations = []
