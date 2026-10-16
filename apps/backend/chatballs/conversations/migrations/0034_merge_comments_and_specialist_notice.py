"""Join accepted comment storage and collaboration migration histories."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_merge_comments_participants"),
        ("conversations", "0033_specialist_joined_event"),
    ]
    operations = []
