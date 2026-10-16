"""Join assistance send guards with the accepted turn diagnostic guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0043_merge_assistance_participant_guards"),
        ("tenancy", "0044_merge_comments_diagnostics"),
        ("tenancy", "0043_turn_diagnostic_guards"),
        ("tenancy", "0045_reply_suggestion_send_guards"),
        ("ai", "0027_merge_assistance_diagnostics"),
    ]

    operations = []
