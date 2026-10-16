"""Join internal history and the independently accepted fact journal."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_merge_comments_participants"),
        ("conversations", "0032_domain_event_data"),
    ]
    operations = []
