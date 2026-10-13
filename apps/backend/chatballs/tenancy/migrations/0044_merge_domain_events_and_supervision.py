"""Keep both event-journal and supervisor tenant guards in one migration graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_domain_event_guards"),
        ("tenancy", "0043_supervision_guards"),
    ]

    operations = []
