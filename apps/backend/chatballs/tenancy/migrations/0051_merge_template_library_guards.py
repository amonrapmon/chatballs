"""Preserve template guards alongside the current tenant migration history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_template_library_guards"),
        ("tenancy", "0050_merge_work_status_ui_main"),
        ("conversations", "0034_merge_template_libraries"),
    ]
    operations = []
