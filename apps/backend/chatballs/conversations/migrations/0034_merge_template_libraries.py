"""Join template libraries with the current conversation history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_template_libraries"),
        ("conversations", "0033_merge_domain_events_comments"),
    ]
    operations = []
