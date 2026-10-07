"""New participation history starts empty; existing assignments remain intact."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0030_transfer_data"),
        ("identity", "0042_organization_participant_limit"),
    ]
    operations = [
        migrations.CreateModel(
            name="ConversationParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("join_reason", models.TextField()),
                ("left_at", models.DateTimeField(blank=True, null=True)),
                ("leave_reason", models.TextField(blank=True, default="")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="conversations.conversation")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conversation_participations", to="identity.organizationmembership")),
                ("joined_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organizationmembership")),
                ("left_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organizationmembership")),
            ],
            options={
                "ordering": ["-joined_at", "-id"],
                "indexes": [models.Index(fields=["organization", "conversation", "-joined_at", "-id"], name="participant_history_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("conversation", "membership"), condition=models.Q(left_at__isnull=True), name="uniq_active_conversation_member"),
                    models.CheckConstraint(condition=~models.Q(join_reason=""), name="participant_join_reason_required"),
                    models.CheckConstraint(condition=models.Q(left_at__isnull=True, left_by__isnull=True, leave_reason="") | (models.Q(left_at__isnull=False, left_by__isnull=False) & ~models.Q(leave_reason="")), name="participant_leave_details"),
                    models.CheckConstraint(condition=models.Q(left_at__isnull=True) | models.Q(left_at__gte=models.F("joined_at")), name="participant_leave_after_join"),
                ],
            },
        ),
    ]
