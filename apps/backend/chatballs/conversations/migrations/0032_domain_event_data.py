"""Empty fact journal and an explicit database-time history boundary."""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Now


class Migration(migrations.Migration):
    dependencies = [("conversations", "0031_participant_data")]
    operations = [
        migrations.CreateModel(
            name="ConversationEventHistoryStart",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("available_from", models.DateTimeField(db_default=Now(), editable=False)),
            ],
            options={"constraints": [models.CheckConstraint(condition=models.Q(id=1), name="domain_history_singleton")]},
        ),
        migrations.CreateModel(
            name="ConversationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("ACCEPTED", "Accepted"), ("ASSIGNED", "Assigned"), ("TRANSFERRED", "Transferred"), ("QUEUE_ENTERED", "Queue Entered"), ("QUEUE_EXITED", "Queue Exited"), ("PUBLIC_REPLY", "Public Reply"), ("CLOSED", "Closed"), ("FOLLOW_UP", "Follow Up")], max_length=20)),
                ("occurred_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("sequence", models.PositiveBigIntegerField(db_default=1, editable=False)),
                ("operation_id", models.UUIDField()),
                ("actor_kind", models.CharField(choices=[("HUMAN", "Human"), ("AI", "Ai"), ("CONTACT", "Contact"), ("SYSTEM", "System")], max_length=8)),
                ("initiated_by_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("responsible_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("group_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("connection_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("transport", models.CharField(blank=True, choices=[("MAX", "Max"), ("TELEGRAM", "Telegram"), ("VK", "Vk"), ("WEB", "Web"), ("EMAIL", "Email")], max_length=8, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domain_events", to="conversations.conversation")),
            ],
            options={
                "ordering": ["conversation_id", "sequence"],
                "indexes": [models.Index(fields=["organization", "occurred_at"], name="domain_event_period_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("conversation", "sequence"), name="uniq_domain_event_sequence"),
                    models.UniqueConstraint(fields=("organization", "operation_id", "event_type"), name="uniq_domain_event_operation"),
                    models.CheckConstraint(condition=models.Q(sequence__gt=0), name="domain_event_sequence_positive"),
                    models.CheckConstraint(condition=models.Q(event_type__in=["ACCEPTED", "ASSIGNED", "TRANSFERRED", "QUEUE_ENTERED", "QUEUE_EXITED", "PUBLIC_REPLY", "CLOSED", "FOLLOW_UP"]), name="domain_event_type_valid"),
                    models.CheckConstraint(condition=models.Q(actor_kind__in=["HUMAN", "AI", "CONTACT", "SYSTEM"]), name="domain_event_actor_valid"),
                    models.CheckConstraint(condition=models.Q(transport__isnull=True) | models.Q(transport__in=["MAX", "TELEGRAM", "VK", "WEB", "EMAIL"]), name="domain_event_transport_valid"),
                    models.CheckConstraint(condition=models.Q(connection_id__isnull=True, transport__isnull=True) | models.Q(connection_id__isnull=False, transport__isnull=False), name="domain_event_connection_pair"),
                ],
            },
        ),
        # No reads of old conversations/messages, and no invented events.
        migrations.RunSQL(
            "INSERT INTO conversations_conversationeventhistorystart (id, available_from) VALUES (1, clock_timestamp())",
            "DELETE FROM conversations_conversationeventhistorystart WHERE id = 1",
        ),
    ]
