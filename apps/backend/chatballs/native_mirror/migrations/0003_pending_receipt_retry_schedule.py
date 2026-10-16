"""Persist a bounded retry schedule for pending native receipts."""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("native_mirror", "0002_gateway_publication"),
    ]

    operations = [
        migrations.AddField(
            model_name="nativemirrorreceipt",
            name="next_attempt_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddIndex(
            model_name="nativemirrorreceipt",
            index=models.Index(
                fields=["organization", "status", "next_attempt_at"],
                name="native_mirror_due_idx",
            ),
        ),
    ]
