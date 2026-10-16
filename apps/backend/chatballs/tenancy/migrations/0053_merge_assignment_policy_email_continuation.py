"""Join assignment guards with the current tenant protection history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0046_assignment_transfer_guards"),
        ("tenancy", "0052_merge_email_continuation_guards"),
    ]
    operations = []
