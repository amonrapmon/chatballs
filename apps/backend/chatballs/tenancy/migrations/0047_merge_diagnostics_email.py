"""Keep accepted diagnostics alongside the email continuation tenant guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_diagnostics_observations"),
        ("tenancy", "0046_email_followup_guards"),
    ]

    operations = []
