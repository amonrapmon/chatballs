from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0059_merge_transfer_participation_ui"),
        ("tenancy", "0046_email_followup_guards"),
        ("conversations", "0041_merge_mail_followup_main"),
    ]
    operations = []
