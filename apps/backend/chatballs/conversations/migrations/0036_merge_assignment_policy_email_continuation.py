"""Join the accepted assignment policy with the current conversation schema."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0034_initial_assignment_policy"),
        ("conversations", "0035_merge_email_continuation"),
    ]
    operations = []
