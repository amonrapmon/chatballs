"""Join assignment guards with accepted visitor and quality protections."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0053_merge_assignment_policy_email_continuation"),
        ("tenancy", "0054_merge_visitor_and_quality_guards"),
    ]
    operations = []
