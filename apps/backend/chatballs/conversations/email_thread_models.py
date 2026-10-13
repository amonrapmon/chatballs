"""Additional mail transport; never replaces the WEB conversation's source."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class EmailThread(TenantRelationModel):
    tenant_relation_fields = ("conversation", "connection", "previous_thread")
    previous_thread = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="followups",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="email_threads",
    )
    connection = models.ForeignKey(
        "integrations.Integration", on_delete=models.PROTECT, related_name="email_threads",
    )
    recipient = models.EmailField()
    subject = models.CharField(max_length=998)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(recipient=""), name="email_thread_recipient_required"),
            models.CheckConstraint(condition=~models.Q(subject=""), name="email_thread_subject_required"),
        ]

    def validate_tenant_relations(self):
        from chatballs.conversations.models import ConnectionIdentity

        super().validate_tenant_relations()
        if self.connection.provider != "EMAIL" or self.connection.kind != "MESSENGER":
            raise ValidationError("email_thread_invalid_connection")
        if self._state.adding:
            if self.previous_thread_id:
                previous = self.previous_thread
                if (
                    previous.connection_id != self.connection_id or previous.recipient != self.recipient
                    or previous.subject != self.subject
                    or self.conversation.previous_conversation_id != previous.conversation_id
                    or previous.conversation.lifecycle == "OPEN"
                    or self.conversation.contact_id != previous.conversation.contact_id
                    or self.conversation.connection_id != previous.conversation.connection_id
                    or self.conversation.channel_id != previous.conversation.channel_id
                ):
                    raise ValidationError("email_thread_invalid_followup")
                return
            if not self.connection.is_active:
                raise ValidationError("email_thread_inactive_connection")
            conversation = self.conversation
            if not conversation.connection_id or conversation.connection.provider != "WEB":
                raise ValidationError("email_thread_requires_web_source")
            recipient = self.recipient.strip().lower()
            try:
                validate_email(recipient)
            except ValidationError as error:
                raise ValidationError("email_thread_invalid_recipient") from error
            contact = conversation.contact
            saved_address = contact and contact.email.strip().lower() == recipient
            saved_identity = contact and ConnectionIdentity.objects.filter(
                organization_id=self.organization_id, contact=contact,
                connection__provider="EMAIL", external_user_id__iexact=recipient,
            ).exists()
            if not saved_address and not saved_identity:
                raise ValidationError("email_thread_recipient_not_saved")
            self.recipient = recipient


class EmailMessageDirection(models.TextChoices):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class EmailThreadMessage(TenantRelationModel):
    """Mailbox-scoped Message-ID registry and actual transport of a message."""

    tenant_relation_fields = ("thread", "connection", "message")
    thread = models.ForeignKey(EmailThread, on_delete=models.CASCADE, related_name="letters")
    connection = models.ForeignKey("integrations.Integration", on_delete=models.PROTECT)
    message = models.OneToOneField(
        "conversations.Message", on_delete=models.CASCADE, related_name="email_transport",
    )
    direction = models.CharField(max_length=8, choices=EmailMessageDirection.choices)
    mail_message_id = models.CharField(max_length=998)
    in_reply_to = models.CharField(max_length=998, blank=True, default="")
    references = models.JSONField(default=list, blank=True)
    sender_address = models.EmailField(blank=True, default="")
    recipient_address = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=998, blank=True, default="")
    mailbox_name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "mail_message_id"], name="uniq_email_mailbox_message_id"),
            models.CheckConstraint(condition=~models.Q(mail_message_id=""), name="email_message_id_required"),
            models.CheckConstraint(
                condition=models.Q(direction__in=EmailMessageDirection.values), name="email_message_direction_valid",
            ),
        ]

    def validate_tenant_relations(self):
        super().validate_tenant_relations()
        if self.connection_id != self.thread.connection_id:
            raise ValidationError("email_message_mailbox_mismatch")
        if self.message.conversation_id != self.thread.conversation_id:
            raise ValidationError("email_message_conversation_mismatch")
