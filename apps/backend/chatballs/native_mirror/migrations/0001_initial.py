import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("conversations", "0032_merge_gateway_and_participant_data"),
        ("integrations", "0015_merge_gateway_and_external_tools"),
    ]

    operations = [
        migrations.CreateModel(
            name="NativeMirrorConversationState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("revision", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("conversation", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="native_mirror_state",
                    to="conversations.conversation",
                )),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="identity.organization",
                )),
            ],
        ),
        migrations.CreateModel(
            name="NativeMirrorReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=32)),
                ("source_id", models.CharField(max_length=128)),
                ("event_id", models.CharField(max_length=256)),
                ("external_chat_id", models.CharField(max_length=128)),
                ("external_message_id", models.CharField(max_length=128)),
                ("payload_hash", models.CharField(max_length=64)),
                ("occurred_at", models.DateTimeField()),
                ("external_reply_to_id", models.CharField(blank=True, max_length=128)),
                ("pending_text", models.TextField(blank=True)),
                ("status", models.CharField(
                    choices=[("PENDING", "Awaiting conversation"),
                             ("STORED", "Stored in conversation"),
                             ("SELF_ECHO", "Known own outbound"),
                             ("UNCLASSIFIED", "Unknown external origin")],
                    default="PENDING", max_length=20,
                )),
                ("reason", models.CharField(blank=True, max_length=48)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("author_user", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL,
                )),
                ("conversation", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="native_mirror_receipts", to="conversations.conversation",
                )),
                ("integration", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="native_mirror_receipts", to="integrations.integration",
                )),
                ("message", models.OneToOneField(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="conversations.message",
                )),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="identity.organization",
                )),
            ],
            options={
                "indexes": [
                    models.Index(fields=["organization", "status", "received_at"],
                                 name="native_mirror_pending_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("integration", "event_id"),
                                            name="native_mirror_unique_event"),
                    models.UniqueConstraint(
                        fields=("integration", "external_chat_id", "external_message_id"),
                        name="native_mirror_unique_provider_message",
                    ),
                    models.CheckConstraint(
                        condition=(
                            ~models.Q(status="STORED")
                            | models.Q(message__isnull=False, conversation__isnull=False)
                        ),
                        name="native_mirror_stored_has_message",
                    ),
                ],
            },
        ),
    ]
