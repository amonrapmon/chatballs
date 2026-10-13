"""Join independently accepted comment and work-status guard branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_comments_participants"),
        ("tenancy", "0043_merge_work_status_participant_guards"),
    ]
    operations = []
