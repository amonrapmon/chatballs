"""Apply all accepted guard branches without changing their protections."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0033_merge_comments_domain_events"),
        ("tenancy", "0045_merge_supervision_work_status"),
        ("tenancy", "0043_domain_event_guards"),
    ]
    operations = []
