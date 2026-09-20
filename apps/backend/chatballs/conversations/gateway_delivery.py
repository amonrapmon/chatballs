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
    MessageKind,
)
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import t
from chatballs.integrations.models import IntegrationProvider
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

GATEWAY_DELIVERY_COMMAND_REQUESTED = "gateway.delivery_command.requested.v1"


class GatewayDeliveryError(Exception):
    pass


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
        connection = locked_conversation.connection
        config = connection.config if connection else None
        source_id = config.get("source_id") if isinstance(config, dict) else None
        source_id = source_id.strip() if isinstance(source_id, str) else ""
        external_chat_id = (locked_conversation.external_chat_id or "").strip()
        if (
            connection is None
            or connection.provider != IntegrationProvider.GATEWAY
            or not source_id
            or not external_chat_id
            or locked_conversation.lifecycle != LifecycleState.OPEN
        ):
            raise GatewayDeliveryError(t("conversations.gateway_delivery_unavailable"))

        identity = ConnectionIdentity.objects.filter(
            connection=connection,
            contact=locked_conversation.contact,
        ).first()
        message = Message.objects.create(
            conversation=locked_conversation,
            author_type=MessageAuthor.OPERATOR,
            author_user=context.actor_user,
            kind=MessageKind.TEXT,
            text=text,
        )
        locked_conversation.last_activity_at = timezone.now()
        locked_conversation.expected_responder = ExpectedResponder.CUSTOMER
        locked_conversation.save(update_fields=["last_activity_at", "expected_responder"])

        enqueue_event(
            DomainEvent(
                aggregate_type="Message",
                aggregate_id=str(message.id),
                event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
                payload={
                    "integration_id": connection.id,
                    "command": {
                        "schema": "intercom-gw.delivery-command.v1",
                        "command_id": str(uuid.uuid4()),
                        "source_id": source_id,
                        "recipient": {
                            "external_chat_id": external_chat_id,
                            "external_user_id": (
                                identity.external_user_id if identity else None
                            ),
                        },
                        "message": {"kind": "text", "text": message.text},
                    },
                },
                tenant_context=context,
            )
        )
        return message
