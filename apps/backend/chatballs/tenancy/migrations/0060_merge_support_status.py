"""Keep every published guard and the atomic work-status block cut."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0046_merge_support_status"),
        ("tenancy", "0059_merge_transfer_participation_ui"),
        ("tenancy", "0047_work_status_block_stop"),
    ]
    operations = []
