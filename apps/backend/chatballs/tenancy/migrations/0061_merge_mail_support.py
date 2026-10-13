from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0060_merge_mail_followup_main"),
        ("tenancy", "0060_merge_support_status"),
        ("conversations", "0042_merge_mail_support"),
    ]
    operations = []
