"""Keep the deployed rating dependency and current main tenant protections."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0045_merge_domain_events"),
        ("tenancy", "0059_merge_transfer_participation_ui"),
    ]
    operations = []
