"""Join the assignment policy with the newly accepted quality schema."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0036_merge_assignment_policy_email_continuation"),
        ("conversations", "0036_merge_quality_data"),
    ]
    operations = []
