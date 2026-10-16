"""Preserve supervision, support facts and mail tenant guards together."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_supervision_guards"),
        ("tenancy", "0043_domain_event_guards"),
        ("tenancy", "0043_email_continuation_guards"),
    ]
    operations = []
