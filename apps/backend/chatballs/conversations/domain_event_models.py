"""Support facts: typed identifiers only, independent of message/audit content."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Now

from chatballs.tenancy.models import TenantRelationModel


class ConversationEventType(models.TextChoices):
    ACCEPTED = "ACCEPTED"
    ASSIGNED = "ASSIGNED"
    TRANSFERRED = "TRANSFERRED"
    QUEUE_ENTERED = "QUEUE_ENTERED"
    QUEUE_EXITED = "QUEUE_EXITED"
    PUBLIC_REPLY = "PUBLIC_REPLY"
    CLOSED = "CLOSED"
    FOLLOW_UP = "FOLLOW_UP"


class ConversationEventActor(models.TextChoices):
    HUMAN = "HUMAN"
    AI = "AI"
    CONTACT = "CONTACT"
    SYSTEM = "SYSTEM"


class ConversationEventTransport(models.TextChoices):
    MAX = "MAX"
    TELEGRAM = "TELEGRAM"
    VK = "VK"
    WEB = "WEB"
    EMAIL = "EMAIL"
    API_CONNECTOR = "API_CONNECTOR"


class ConversationEvent(TenantRelationModel):
    tenant_relation_fields = ("conversation",)
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="domain_events"
    )
    event_type = models.CharField(max_length=20, choices=ConversationEventType.choices)
    # The database INSERT trigger sets both, including for bulk/raw inserts.
    occurred_at = models.DateTimeField(db_default=Now(), editable=False)
    sequence = models.PositiveBigIntegerField(db_default=1, editable=False)
    operation_id = models.UUIDField()
    actor_kind = models.CharField(max_length=8, choices=ConversationEventActor.choices)
    # Snapshots are checked against the tenant on INSERT, but deliberately have
    # no FK to mutable dimensions: removing a member/group/connection must not
    # erase historical attribution or prevent their ordinary deletion.
    initiated_by_id = models.PositiveBigIntegerField(null=True, blank=True)
    responsible_id = models.PositiveBigIntegerField(null=True, blank=True)
    group_id = models.PositiveBigIntegerField(null=True, blank=True)
    connection_id = models.PositiveBigIntegerField(null=True, blank=True)
    transport = models.CharField(
        max_length=16, choices=ConversationEventTransport.choices, null=True, blank=True
    )

    class Meta:
        ordering = ["conversation_id", "sequence"]
        indexes = [
            models.Index(fields=["organization", "occurred_at"], name="domain_event_period_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sequence"], name="uniq_domain_event_sequence"
            ),
            # One domain operation can emit several distinct kinds of fact.
            models.UniqueConstraint(
                fields=["organization", "operation_id", "event_type"],
                name="uniq_domain_event_operation",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gt=0), name="domain_event_sequence_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(event_type__in=ConversationEventType.values),
                name="domain_event_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(actor_kind__in=ConversationEventActor.values),
                name="domain_event_actor_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(transport__isnull=True)
                | models.Q(transport__in=ConversationEventTransport.values),
                name="domain_event_transport_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(connection_id__isnull=True, transport__isnull=True)
                | models.Q(connection_id__isnull=False, transport__isnull=False),
                name="domain_event_connection_pair",
            ),
        ]

    def validate_tenant_relations(self):
        from chatballs.identity.group_models import EmployeeGroup
        from chatballs.identity.models import OrganizationMembership
        from chatballs.integrations.models import Integration, IntegrationKind

        super().validate_tenant_relations()
        for field, model, lookup in (
            ("initiated_by_id", OrganizationMembership, "user_id"),
            ("responsible_id", OrganizationMembership, "user_id"),
            ("group_id", EmployeeGroup, "pk"),
            ("connection_id", Integration, "pk"),
        ):
            value = getattr(self, field)
            if value is not None and not model.objects.filter(
                organization_id=self.organization_id, **{lookup: value}
            ).exists():
                raise ValidationError("Domain event dimension must belong to the organization")
        if self.connection_id is not None and not Integration.objects.filter(
            pk=self.connection_id, organization_id=self.organization_id,
            kind=IntegrationKind.MESSENGER, provider=self.transport,
        ).exists():
            raise ValidationError("Domain event transport must match its connection")

    def __str__(self):
        return f"domain-event:{self.conversation_id}/{self.sequence}/{self.event_type}"


class ConversationEventHistoryStart(models.Model):
    """Installation-wide storage boundary; not proof all sources are connected.

    A reporting service must also account for source coverage and conversations
    predating this boundary. No intervals before it can be reconstructed.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    available_from = models.DateTimeField(db_default=Now(), editable=False)
    # Conservative reporting deployment boundary: sources are now installed.
    sources_available_from = models.DateTimeField(db_default=Now(), editable=False)
    status_stops_available_from = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="domain_history_singleton"),
        ]

    def __str__(self):
        return f"domain-history:{self.available_from}"
