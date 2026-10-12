"""Durable pre-send decision for Gateway AI messages."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("native_mirror", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NativeMirrorPublication",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("revision", models.PositiveBigIntegerField()),
                ("status", models.CharField(
                    choices=[
                        ("QUEUED", "Awaiting dispatch claim"),
                        ("CLAIMED", "Dispatch attempted or may have started"),
                        ("SUPPRESSED", "Cancelled before dispatch claim"),
                    ],
                    default="QUEUED", max_length=16,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("suppressed_at", models.DateTimeField(blank=True, null=True)),
                ("message", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="native_mirror_publication",
                    to="conversations.message",
                )),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="identity.organization",
                )),
            ],
        ),
    ]
