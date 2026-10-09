from __future__ import annotations

import uuid

from django.utils import timezone

from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
    DeliveryStatus,
    MessageKind,
)
from chatballs.events.models import OutboxEvent
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import t
from chatballs.integrations.models import IntegrationProvider
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

GATEWAY_DELIVERY_COMMAND_REQUESTED = "gateway.delivery_command.requested.v1"


class GatewayDeliveryError(Exception):
    pass


def enqueue_gateway_delivery(*, context: TenantContext, message: Message) -> None:
    """Enqueue an existing message using the caller's tenant transaction.

    A command ID and its outbox event are committed together. A repeat call
    for the same message keeps the previously stored command, not a new send.
    """
    if message.pk is None:
        raise GatewayDeliveryError("Gateway message must be saved before enqueue")

    persisted = Message.objects.select_for_update(of=("self",)).get(pk=message.pk)
    conversation = persisted.conversation
    if conversation.organization_id != context.organization_id:
        raise GatewayDeliveryError(t("conversations.gateway_delivery_unavailable"))
    if persisted.gateway_command_id is not None and OutboxEvent.objects.filter(
        aggregate_type="Message",
        aggregate_id=str(persisted.id),
        event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
    ).exists():
        message.gateway_command_id = persisted.gateway_command_id
        message.delivery_status = persisted.delivery_status
        return

    connection = conversation.connection
    config = connection.config if connection else None
    source_id = config.get("source_id") if isinstance(config, dict) else None
    source_id = source_id.strip() if isinstance(source_id, str) else ""
    external_chat_id = (conversation.external_chat_id or "").strip()
    if (
        connection is None
        or connection.provider != IntegrationProvider.GATEWAY
        or not source_id
        or not external_chat_id
        or conversation.lifecycle != LifecycleState.OPEN
    ):
        raise GatewayDeliveryError(t("conversations.gateway_delivery_unavailable"))

    identity = ConnectionIdentity.objects.filter(
        connection=connection, contact=conversation.contact
    ).first()
    command_id = persisted.gateway_command_id or uuid.uuid4()
    if persisted.gateway_command_id is None:
        persisted.gateway_command_id = command_id
        persisted.delivery_status = DeliveryStatus.QUEUED
        persisted.save(update_fields=["gateway_command_id", "delivery_status"])
    message.gateway_command_id = command_id
    message.delivery_status = persisted.delivery_status

    enqueue_event(
        DomainEvent(
            aggregate_type="Message",
            aggregate_id=str(persisted.id),
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            payload={
                "integration_id": connection.id,
                "command": {
                    "schema": "intercom-gw.delivery-command.v1",
                    "command_id": str(command_id),
                    "source_id": source_id,
                    "recipient": {
                        "external_chat_id": external_chat_id,
                        "external_user_id": identity.external_user_id if identity else None,
                    },
                    "message": {"kind": "text", "text": persisted.text},
                },
            },
            tenant_context=context,
        )
    )


def post_gateway_operator_message(
    *, context: TenantContext, conversation: Conversation, text: str
) -> Message:
    """Persist a gateway reply and its delivery command atomically."""

    with tenant_atomic(context):
        locked_conversation = (
            Conversation.objects.select_for_update(of=("self",))
            .select_related("connection")
            .get(id=conversation.id, organization_id=context.organization_id)
        )
        message = Message.objects.create(
            conversation=locked_conversation,
            author_type=MessageAuthor.OPERATOR,
            author_user=context.actor_user,
            kind=MessageKind.TEXT,
            text=text,
            gateway_command_id=uuid.uuid4(),
            delivery_status=DeliveryStatus.QUEUED,
        )
        locked_conversation.last_activity_at = timezone.now()
        locked_conversation.expected_responder = ExpectedResponder.CUSTOMER
        locked_conversation.save(update_fields=["last_activity_at", "expected_responder"])
        enqueue_gateway_delivery(context=context, message=message)
        return message
