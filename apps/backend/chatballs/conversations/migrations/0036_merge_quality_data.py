"""Join quality data with the current conversation migration history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_quality_data"),
        ("conversations", "0035_merge_email_continuation"),
    ]
    operations = []
