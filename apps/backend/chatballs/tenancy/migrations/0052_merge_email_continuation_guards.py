"""Keep mail guards alongside the current tenant migration history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_email_continuation_guards"),
        ("tenancy", "0051_merge_template_library_guards"),
        ("conversations", "0035_merge_email_continuation"),
    ]
    operations = []
