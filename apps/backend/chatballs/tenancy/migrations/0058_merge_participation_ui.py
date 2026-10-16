from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0053_merge_participation_ui_dependencies"),
        ("tenancy", "0057_merge_assignment_participant"),
        ("conversations", "0039_merge_participation_ui"),
    ]
    operations = []
