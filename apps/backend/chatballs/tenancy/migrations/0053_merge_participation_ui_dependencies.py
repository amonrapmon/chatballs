"""Preserve both sets of tenant guards; no permissions are replaced."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0045_merge_comments_diagnostics_and_collaboration"),
        ("tenancy", "0052_merge_email_continuation_guards"),
        ("conversations", "0036_merge_participation_ui_dependencies"),
    ]
    operations = []
