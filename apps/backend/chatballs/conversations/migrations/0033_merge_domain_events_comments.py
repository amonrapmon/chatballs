"""Join domain facts with the accepted comment and participant histories."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_domain_event_data"),
        ("conversations", "0032_merge_comments_participants"),
    ]
    operations = []
